import os
import requests
import logging
import secrets
import ssl
import sqlite3
import subprocess
import platform
import time
from urllib.parse import quote_plus
from flask import Flask, redirect, url_for, session, request, render_template, jsonify, flash, abort, make_response
from flask_login import login_user

from models import *
from authlib.integrations.flask_client import OAuth, OAuthError
from functools import wraps
from waitress import serve
from flask_session import Session
from requests.auth import HTTPBasicAuth
# from dashboard import dashboard_bp  # Disabled - using new architecture  # Legacy dashboard routes
from dashboard_routes import dashboard_bp as new_dashboard_bp  # New dashboard architecture
from dashboards.api import api_bp as dashboard_api_bp  # Dashboard API
from admin import admin_bp  # Admin panel
from survey import survey_bp  # Survey system
# from tools import tools_bp
import json
from auth_utils import requires_auth
from fetch_data.faculty_main import get_faculty_details_by_markaz
from flask import g
from flask_login import current_user, login_required, LoginManager, UserMixin
# from .forms import TaskForm
from kanban import kanban_bp
# from flask_migrate import Migrate
from students_dashboard import students_bp
from collections import defaultdict
from dotenv import load_dotenv

# Load environment variables from .env file FIRST, before importing modules that need them
# Try multiple locations: project root, app directory, and current directory
BASE_DIR_ENV = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR_ENV)  # Go up one level from app/ to project root
# Try loading from multiple locations (order matters - first found wins)
load_dotenv(dotenv_path=os.path.join(PROJECT_ROOT, '.env'))  # Project root
load_dotenv(dotenv_path=os.path.join(BASE_DIR_ENV, '.env'))  # app/ directory
load_dotenv()  # Current directory (fallback)

from extensions import db
import hashlib
import jdatetime
from datetime import datetime, timedelta
import datetime as dt
import pytz
from send_sms import get_sms_token, send_sms

def get_color_for_key(key: str) -> str:
    """Generate a bright color hex code based on a key string."""
    # Use MD5 hash to get a consistent number
    h = hashlib.md5(key.encode()).hexdigest()
    # Take first 6 hex digits for color
    color = f"#{h[:6]}"
    return color
    
# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, template_folder="templates")
# SECRET_KEY must be set as environment variable for security
secret_key = os.environ.get("SECRET_KEY")
if not secret_key:
    raise ValueError(
        "SECRET_KEY environment variable is not set. "
        "Please set it in your .env file or environment variables."
    )
app.secret_key = secret_key

# Configure Jinja2 for template auto-reload in development
# In production, templates are cached for performance, but we want to detect file changes
import os
is_development = os.environ.get('FLASK_ENV') == 'development' or os.environ.get('FLASK_DEBUG') == '1'
app.jinja_env.auto_reload = is_development
# Always check for template updates (even in production) - this is safe and ensures changes are detected
app.jinja_env.cache_size = 50  # Limit cache size
logger.info(f"Jinja2 template auto_reload: {is_development}, cache_size: {app.jinja_env.cache_size}")

# Error handler for JSON requests
@app.errorhandler(500)
def handle_500_error(e):
    """Handle 500 errors - return JSON for API requests, HTML for others"""
    import traceback
    error_traceback = traceback.format_exc()
    logger.error(f"500 Error in {request.path}: {e}")
    logger.error(f"Traceback: {error_traceback}")
    
    # CRITICAL: For admin template edit pages, return HTML error page directly
    # Blueprint error handler should catch it, but if it doesn't, we handle it here
    if request.path.startswith('/admin/dashboards/templates/'):
        path_parts = request.path.split('/')
        if len(path_parts) >= 5:
            template_name = path_parts[4]
            # If it's a template file (ends with .html) and GET request
            if template_name.endswith('.html') and request.method == 'GET':
                # Return HTML error page directly - don't let it fall through to JSON
                from flask import Response
                import traceback
                error_traceback = traceback.format_exc()
                error_html = f"""<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
    <meta charset="utf-8">
    <title>خطا در ویرایش تمپلیت</title>
    <style>
        body {{ font-family: Tahoma, Arial; padding: 20px; background: #f5f5f5; }}
        .error-box {{ background: white; padding: 20px; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        h1 {{ color: #d32f2f; }}
        pre {{ background: #f5f5f5; padding: 10px; border-radius: 3px; overflow-x: auto; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="error-box">
        <h1>خطا در نمایش صفحه ویرایش</h1>
        <p><strong>تمپلیت:</strong> {template_name}</p>
        <p><strong>خطا:</strong> {str(e)}</p>
        <details>
            <summary>جزئیات خطا (برای توسعه‌دهندگان)</summary>
            <pre>{error_traceback}</pre>
        </details>
        <p><a href="/admin/dashboards/templates">بازگشت به لیست تمپلیت‌ها</a></p>
    </div>
</body>
</html>"""
                return Response(error_html, status=500, mimetype='text/html; charset=utf-8')
    
    # For API endpoints only, return JSON (not for HTML pages even if they accept JSON)
    # Check if this is explicitly an API endpoint
    is_api_endpoint = (
        request.path.startswith('/charts-data') or 
        request.path.startswith('/tables-data') or
        request.path.startswith('/api/')
    )
    
    # Only return JSON for explicit API endpoints, not for HTML pages
    if is_api_endpoint:
        return jsonify({
            "error": "خطا در دریافت داده‌ها",
            "message": str(e) if hasattr(e, '__str__') else "خطای داخلی سرور"
        }), 500
    
    # For all other requests (including admin template pages that didn't match above),
    # return None to use default Flask error handling or let route handle it
    # This ensures HTML error pages are returned, not JSON
    return None

app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_COOKIE_SECURE"] = True      # Ensures cookies are only sent over HTTPS
app.config["SESSION_COOKIE_HTTPONLY"] = True    # Prevents JavaScript access to cookies
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"   # Adjust as needed (Lax/Strict/None)
# app.secret_key = 'your_secret'
BASE_DIR = os.path.abspath(os.path.dirname(__file__))  # Directory where this script lives
DB_PATH = f"sqlite:///{os.path.join(BASE_DIR, 'access_control.db')}"

app.config['SQLALCHEMY_DATABASE_URI'] = DB_PATH
# app.config['UPLOAD_FOLDER'] = './uploads'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static/uploads')

db.init_app(app)

# Import admin models to register them with SQLAlchemy
from admin_models import DashboardAccess, AccessLog, DataSync, DashboardConfig

from label_management import label_bp
app.register_blueprint(label_bp)

from task_label_assignment import assignment_bp
app.register_blueprint(assignment_bp)

# Register your dashboard routes
# Note: Using new architecture only
app.register_blueprint(new_dashboard_bp)  # New architecture routes
app.register_blueprint(dashboard_api_bp)  # Dashboard API for filters
app.register_blueprint(admin_bp)  # Admin panel
app.register_blueprint(survey_bp)  # Survey system
# app.register_blueprint(dashboard_bp)  # Legacy routes - DISABLED (using new architecture)

# Start auto-sync scheduler
try:
    with app.app_context():
        from admin.scheduler import start_scheduler
        start_scheduler()
        logger.info("Auto-sync scheduler initialized")
except Exception as e:
    logger.error(f"Failed to start auto-sync scheduler: {e}", exc_info=True)

# Context processor to make dashboard list available in all templates
@app.context_processor
def inject_dashboards():
    """Make dashboard list and user info available in all templates"""
    from dashboards.registry import DashboardRegistry
    from dashboards.context import get_user_context
    import jdatetime
    from datetime import datetime
    try:
        if current_user.is_authenticated:
            user_context = get_user_context()
            dashboards = DashboardRegistry.get_accessible_dashboards(user_context)
            user_info = session.get('user_info', {})
            return {
                'accessible_dashboards': dashboards,
                'current_user_info': user_info,
                'user_context': user_context.to_dict() if user_context else {},
                'jdatetime': jdatetime,
                'current_year': jdatetime.datetime.now().year
            }
    except Exception as e:
        logger.warning(f"Error in context processor: {e}")
    return {
        'accessible_dashboards': [],
        'current_user_info': {},
        'user_context': {},
        'jdatetime': jdatetime,
        'current_year': jdatetime.datetime.now().year
    }

# Mock SSO for local testing (only in DEBUG mode)
if app.config.get('DEBUG'):
    from mock_sso import mock_sso_login
    
    @app.route('/mock_login')
    def mock_login():
        """Mock SSO login for local testing"""
        username = request.args.get('username', 'test_central')
        access_level = request.args.get('access_level', 'central_org')
        province_code = request.args.get('province_code', type=int)
        faculty_code = request.args.get('faculty_code', type=int)
        return mock_sso_login(username, access_level, province_code, faculty_code)
app.register_blueprint(students_bp)


Session(app)
# Initialize LoginManager
login_manager = LoginManager()
login_manager.login_view = 'login'  # the endpoint name for your login route
login_manager.init_app(app)

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'exports')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# SSO Configuration - all sensitive values must come from environment variables
SSO_CLIENT_SECRET = os.getenv("SSO_CLIENT_SECRET")
if not SSO_CLIENT_SECRET:
    raise ValueError(
        "SSO_CLIENT_SECRET environment variable is not set. "
        "Please set it in your .env file or environment variables."
    )

SSO_CONFIG = {
    "client_id": os.getenv("SSO_CLIENT_ID", "bicfu"),
    "client_secret": SSO_CLIENT_SECRET,
    "authorize_url": os.getenv("SSO_AUTH_URL", "https://sso.cfu.ac.ir/oauth2/authorize"),
    "access_token_url": os.getenv("SSO_TOKEN_URL", "https://sso.cfu.ac.ir/oauth2/token"),
    "userinfo_url": "https://sso.cfu.ac.ir/oauth2/userinfo",
    "scope": os.getenv("SSO_SCOPE", "profile email"),
    "redirect_uri": os.getenv("SSO_REDIRECT_URI", "https://bi.cfu.ac.ir/authorized"),
}

# Paths to SSL certificates (if needed)
# SSL_CERT_PATH = "C:/nginx/certs/cfu.ac.ir-cert.pem"
# SSL_KEY_PATH = "C:/nginx/certs/private.pem"

# Initialize Authlib OAuth
oauth = OAuth(app)
oauth.register(
    name="sso",
    client_id=SSO_CONFIG["client_id"],
    client_secret=SSO_CONFIG["client_secret"],
    authorize_url=SSO_CONFIG["authorize_url"],
    access_token_url=SSO_CONFIG["access_token_url"],
    # api_base_url='https://sso.cfu.ac.ir/oauth2/',  # optional base
    userinfo_endpoint='https://sso.cfu.ac.ir/oauth2/userinfo',  # ✅ add this
    redirect_uri=SSO_CONFIG["redirect_uri"],
    jwks={
        'keys':[]
    },
    client_kwargs={
        'scope': SSO_CONFIG["scope"]
        
    }
)

@app.route("/")
@requires_auth
def index():
    try:
        user_info = session.get("user_info")
        if not user_info:
            token = session.get("sso_token")
            if not token:
                return redirect(url_for("login"))
            access_token = token.get("access_token")
            user_info = get_user_info(token)
            session["user_info"] = user_info

        # logger.info("Fetched user info: %s", user_info)
        return render_template("index.html", user_info=user_info)

    except Exception as e:
        logger.error("Failed to fetch user info: %s", e)
        return render_template("error.html", error="Failed to fetch user information"), 500

app.register_blueprint(kanban_bp)

# def create_app():
#     app = Flask(__name__)
#     app.secret_key = 'your_secret'
#     app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///access_control.db'
#     app.config['UPLOAD_FOLDER'] = './uploads'

#     db.init_app(app)
#     app.register_blueprint(kanban_bp)

#     @app.before_request
#     def sso_authenticate():
#         # Dummy SSO logic (Replace with your actual SSO logic)
#         session['sso_id'] = 'user123'
#         user = User.query.filter_by(sso_id=session['sso_id']).first()
#         if not user:
#             user = User(sso_id=session['sso_id'], name="Test User")
#             db.session.add(user)
#             db.session.commit()
#         g.current_user = user

#     return app

@app.route("/login")
def login():
    """Initiate SSO authentication."""
    redirect_uri = SSO_CONFIG["redirect_uri"]
    wants_url = request.args.get("next", url_for("index", _external=True))
    sesskey = session.setdefault("sesskey", secrets.token_urlsafe(8))
    user_id = session.setdefault("user_id", 1)  # Replace with proper user logic

    inner = f"https://sso.cfu.ac.ir/oauth2/login.php?wantsurl={quote_plus(wants_url)}&sesskey={sesskey}&id={user_id}"
    state = quote_plus(inner)
    session["oauth_state"] = state

    try:
        logger.info("Initiating SSO login with state: %s", state)
        return oauth.sso.authorize_redirect(redirect_uri, state=state)
    except Exception as e:
        logger.error("Error initiating SSO login: %s", e)
        return render_template("error.html", error="Failed to initiate SSO login"), 500

@app.route("/authorized")
def authorized():
    stored_state = session.get("oauth_state")
    returned_state = request.args.get("state")
    logger.info("Stored state: %s, Returned state: %s", stored_state, returned_state)

    # If state mismatch, it could be due to:
    # 1. Session expired/cleared (user refreshed during auth flow)
    # 2. CSRF attack (legitimate security concern)
    # 3. Multiple login attempts
    
    # Check if user is already authenticated (has sso_token and user_info)
    # If yes, redirect to tools page instead of showing error
    if stored_state != returned_state:
        if session.get("sso_token") and session.get("user_info"):
            # User is already authenticated, just redirect to tools
            logger.warning("State mismatch but user already authenticated, redirecting to tools")
            return redirect(url_for("list_tools"))
        
        # If not authenticated, clear any stale state and redirect to login
        logger.error("CSRF Warning: State mismatch - stored_state=%s, returned_state=%s", stored_state, returned_state)
        session.pop("oauth_state", None)  # Clear stale state
        return redirect(url_for("login"))

    try:
        # token = oauth.sso.authorize_access_token(include_client_id=True)  # Removed withhold_token=True
        token = oauth.sso.authorize_access_token()

        session["sso_token"] = token
        session.pop("oauth_state", None)

        access_token = token.get("access_token")
        if not access_token:
            return render_template("error.html", error="Access token missing")
        # logger.info("Access Token: %s", access_token)

        # userinfo = get_user_info(access_token)
        # userinfo = oauth.sso.get('userinfo').json()
        userinfo = get_user_info(token)

        if "error" in userinfo:
            return render_template("error.html", error="Failed to fetch user info")

        # access_token = token["access_token"]
        session["user_info"] = userinfo
        session["access_token"] = access_token

        # Get access level from userinfo
        username = userinfo.get("username", "").lower()
        access_level = userinfo.get("usertype", "").lower()
        session["access_level"] = [access_level]

        user = User.query.filter_by(sso_id=username).first()
        if not user:
            user = User(sso_id=username, name=userinfo.get("fullname", "Unnamed User"))
            db.session.add(user)
            db.session.commit()
        
        # Check if user should have admin access (from database or environment variable)
        # This allows migration from hardcoded list to database-based access control
        admin_users_env = os.getenv("ADMIN_USERS", "").split(",")
        admin_users_env = [u.strip().lower() for u in admin_users_env if u.strip()]
        
        # Check if user is admin in database
        is_admin = user.is_admin()
        
        # If not in database but in environment variable, grant access
        # This is for backward compatibility during migration
        if not is_admin and username in admin_users_env:
            # Grant admin access in database for future use
            # No longer require access_level to be "staff" - allow any usertype
            admin_access = AccessLevel(level="admin", user_id=user.id)
            db.session.add(admin_access)
            db.session.commit()
            is_admin = True
        
        # Log user info for debugging
        logger.info(f"User login attempt: username={username}, is_admin={is_admin}, access_level={access_level}, usertype={userinfo.get('usertype', 'N/A')}")
        
        # NEW: Tell Flask-Login to log the user in
        login_user(user)

        g.current_user = user

        # Check access: allow admin users to access regardless of usertype
        # Allow all authenticated users to access the system (access control happens at dashboard level)
        if is_admin:
            logger.info(f"Admin user {username} logged in successfully")
            return redirect(url_for("list_tools"))
        else:
            # Allow non-admin users to access as well - they'll have limited access based on their role
            logger.info(f"Regular user {username} logged in successfully")
            return redirect(url_for("list_tools"))

    except OAuthError as e:
        logger.error("OAuth error: %s", e.description)
        return render_template("error.html", error=f"Authorization error: {e.description}"), 400
    except Exception as e:
        logger.exception("Unexpected error on authorized")
        return render_template("error.html", error="Authorization error"), 500

def get_user_info(token):
    try:
        # If token is a string, wrap it as a dict
        if isinstance(token, str):
            token = {"access_token": token, "token_type": "Bearer"}

        userinfo = oauth.sso.get('https://sso.cfu.ac.ir/oauth2/userinfo', token=token).json()
        logger.error(userinfo)
        return userinfo
    except Exception as e:
        logger.error("Error fetching user info: %s", e)
        return {"error": str(e)}


@app.route("/logout")
def logout():
    """Log out the user with proper security and cache control."""
    # Get session cookie name from app config
    session_cookie_name = app.config.get('SESSION_COOKIE_NAME', 'session')
    
    # Clear all session data
    session.clear()
    
    # Log the logout action
    logger.info("User logged out, session cleared.")
    
    # Create response with security headers
    response = redirect("https://sso.cfu.ac.ir/logout?service=https://bi.cfu.ac.ir")
    
    # Prevent caching of logout page
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    # Security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    # Clear session cookie with proper settings
    cookie_secure = app.config.get('SESSION_COOKIE_SECURE', True)
    cookie_httponly = app.config.get('SESSION_COOKIE_HTTPONLY', True)
    cookie_samesite = app.config.get('SESSION_COOKIE_SAMESITE', 'Lax')
    
    response.set_cookie(
        session_cookie_name, 
        '', 
        expires=0, 
        httponly=cookie_httponly, 
        secure=cookie_secure, 
        samesite=cookie_samesite,
        path='/'
    )
    
    return response

@app.template_filter('jalali_date')
def jalali_date_filter(dt_value):
    """Convert datetime to Jalali date string"""
    if not dt_value:
        return None
    try:
        from jdatetime import datetime as jdatetime
        from datetime import datetime as dt_class
        if isinstance(dt_value, str):
            dt_value = dt_class.fromisoformat(dt_value)
        jalali = jdatetime.fromgregorian(datetime=dt_value)
        return jalali.strftime("%Y/%m/%d")
    except Exception:
        return str(dt_value)

@app.route('/survey')
@requires_auth
def survey():
    """Survey page - shows all accessible surveys (public, user_groups, specific_users) for all users including managers"""
    try:
        user_info = session.get("user_info")
        display_name = get_user_display_name(user_info) if user_info else "کاربر گرامی"
        
        from models import User
        from survey.utils import get_accessible_surveys
        
        username = user_info.get('username', '').lower() if user_info else ''
        user = User.query.filter_by(sso_id=username).first() if username else None
        national_id = user_info.get('national_id') if user_info else None
        
        # Get all accessible surveys (public, user_groups, specific_users)
        try:
            surveys = get_accessible_surveys(user, national_id)
        except Exception as e:
            logger.error(f"Error fetching accessible surveys: {e}", exc_info=True)
            surveys = []
        
        response = make_response(render_template(
            "survey/public/list.html",
            user_display_name=display_name,
            surveys=surveys
        ))
        
        # Prevent caching
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        return response
        
    except Exception as e:
        logger.error(f"Error in survey route: {e}", exc_info=True)
        return render_template("error.html", error=f"خطا در بارگذاری صفحه نظرسنجی: {str(e)}"), 500

def get_user_display_name(user_info):
    """Extract user display name from user_info dictionary"""
    if not user_info or not isinstance(user_info, dict):
        return "کاربر گرامی"
    
    # Try different field names that SSO might return
    if user_info.get('fullname'):
        return user_info.get('fullname')
    
    firstname = user_info.get('firstname', '')
    lastname = user_info.get('lastname', '')
    if firstname or lastname:
        return f"{firstname} {lastname}".strip()
    
    if user_info.get('name'):
        return user_info.get('name')
    
    if user_info.get('preferred_username'):
        return user_info.get('preferred_username')
    
    if user_info.get('username'):
        return user_info.get('username')
    
    return "کاربر گرامی"

def check_user_has_valid_dashboard_access(user_info):
    """
    Check if user has at least one valid dashboard access permission
    Admin users always have access regardless of DashboardAccess records
    
    Args:
        user_info: Dictionary containing user information from SSO
        
    Returns:
        bool: True if user has at least one valid dashboard access, False otherwise
    """
    try:
        from admin_models import DashboardAccess
        from models import User
        from datetime import datetime
        
        if not user_info or not isinstance(user_info, dict):
            return False
        
        # Get username from user_info
        username = user_info.get('username', '').lower()
        if not username:
            return False
        
        # Find user in database
        user = User.query.filter_by(sso_id=username).first()
        if not user:
            logger.info(f"User {username} not found in database")
            return False
        
        # Check if user is admin - admins always have access
        admin_users_env = os.getenv("ADMIN_USERS", "").split(",")
        admin_users_env = [u.strip().lower() for u in admin_users_env if u.strip()]
        is_admin = user.is_admin() or username in admin_users_env
        
        if is_admin:
            logger.info(f"User {username} is admin, granting dashboard access")
            return True
        
        # Check if user has any dashboard access records
        access_records = DashboardAccess.query.filter_by(
            user_id=user.id,
            can_access=True
        ).all()
        
        if not access_records:
            logger.info(f"User {username} has no dashboard access records")
            return False
        
        # Check if at least one access record is valid (within date range)
        current_time = datetime.utcnow()
        
        for access in access_records:
            # Check date range if specified
            if access.date_from and access.date_to:
                if access.date_from <= current_time <= access.date_to:
                    logger.info(f"User {username} has valid dashboard access to {access.dashboard_id}")
                    return True
            elif access.date_from:
                # Only start date specified
                if access.date_from <= current_time:
                    logger.info(f"User {username} has valid dashboard access to {access.dashboard_id} (from {access.date_from})")
                    return True
            elif access.date_to:
                # Only end date specified
                if current_time <= access.date_to:
                    logger.info(f"User {username} has valid dashboard access to {access.dashboard_id} (until {access.date_to})")
                    return True
            else:
                # No date restrictions, access is valid
                logger.info(f"User {username} has valid dashboard access to {access.dashboard_id} (no date restrictions)")
                return True
        
        logger.info(f"User {username} has dashboard access records but none are currently valid")
        return False
        
    except Exception as e:
        logger.error(f"Error checking user dashboard access: {e}", exc_info=True)
        return False

@app.route('/tools')
@requires_auth
def list_tools():
    # Check if user has valid session
    # First check if user_info exists, if not, try to get it from token
    user_info = session.get("user_info")
    
    if not user_info:
        # Try to get user info from token if available
        token = session.get("sso_token")
        if token:
            try:
                logger.info("User info not in session, fetching from token")
                user_info = get_user_info(token)
                if user_info and "error" not in user_info:
                    session["user_info"] = user_info
                    logger.info("Successfully fetched user info from token")
                else:
                    logger.warning("Failed to fetch user info from token, redirecting to login")
                    return redirect(url_for('login'))
            except Exception as e:
                logger.error(f"Error fetching user info from token: {e}")
                return redirect(url_for('login'))
        else:
            logging.info("User not authenticated (no token or user_info), redirecting to login")
            return redirect(url_for('login'))
    
    # Log user_info for debugging and extract display name
    if user_info:
        logger.info(f"User info in tools route: {user_info}")
        logger.info(f"User info keys: {list(user_info.keys()) if isinstance(user_info, dict) else 'Not a dict'}")
        display_name = get_user_display_name(user_info)
        logger.info(f"Extracted display name: {display_name}")
        # Ensure display_name is always set
        if not display_name or display_name == "کاربر گرامی":
            # Try to extract from firstname and lastname directly
            if isinstance(user_info, dict):
                firstname = user_info.get('firstname', '')
                lastname = user_info.get('lastname', '')
                if firstname or lastname:
                    display_name = f"{firstname} {lastname}".strip()
                    logger.info(f"Fallback: Using firstname+lastname: {display_name}")
    else:
        logger.warning("User info is None or empty in tools route")
        display_name = "کاربر گرامی"
    
    # Ensure display_name is always set
    if not display_name:
        display_name = "کاربر گرامی"
    
    # Check if user has valid dashboard access
    has_dashboard_access = check_user_has_valid_dashboard_access(user_info)
    logger.info(f"User has valid dashboard access: {has_dashboard_access}")
    
    # Create response with no-cache headers to prevent back button access after logout
    response = make_response(render_template(
        "tools.html", 
        user=user_info, 
        user_display_name=display_name,
        has_dashboard_access=has_dashboard_access
    ))
    
    # Prevent caching - critical for security after logout
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    
    return response

# #######################################
# Projects
# #######################################
@app.route('/projects')
def all_project_list():
    user_info = session.get("user_info")
    sso_id = user_info["username"].lower()
    user = User.query.filter_by(sso_id=sso_id).first()

    if not user:
        flash("کاربر یافت نشد.")
        return redirect(url_for('index'))

    created = Project.query.filter_by(creator_id=user.id).all()

    try:
        involved = Project.query.filter(Project.members.any(id=user.id)).all()
    except Exception as e:
        involved = []
        app.logger.warning(f"Couldn't fetch involved projects: {e}")

    return render_template("projects.html", projects=created, created=created, involved=involved)

from flask import Flask, render_template, request, redirect, url_for
from models import db, Project  # Your SQLAlchemy models


@app.route('/projects/new', methods=['GET', 'POST'])
def new_project():
    if request.method == 'POST':
        # Get all form fields from request.form
        title = request.form.get('title')
        description = request.form.get('description')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        sso_id = request.form.get('sso_id')
        attachment = request.form.get('attachment')
        # created_at = request.form.get('created_at')
        updated_at = request.form.get('updated_at')
        creator_id = request.form.get('creator_id')
        owner_id = request.form.get('owner_id')

        # Validate required fields
        # if not name:
        #     return "Project name is required", 400

        # Convert date strings to Python date/datetime objects if needed
        # from datetime import datetime

        def parse_date(date_str):
            if not date_str:
                return None
            try:
                return datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                return None

        def parse_datetime(datetime_str):
            if not datetime_str:
                return None
            try:
                # datetime-local input format: 'YYYY-MM-DDTHH:MM'
                return datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M")
            except ValueError:
                return None

        start_date = parse_date(start_date)
        end_date = parse_date(end_date)
        # created_at = parse_datetime(created_at) or datetime.utcnow()
        updated_at = parse_datetime(updated_at) or datetime.utcnow()

        # Convert numeric fields
        try:
            creator_id = int(creator_id) if creator_id else None
            owner_id = int(owner_id) if owner_id else None
        except ValueError:
            return "Invalid creator_id or owner_id", 400

        # Create new project object
        new_proj = Project(
            title=title,
            description=description,
            start_date=start_date,
            end_date=end_date,
            sso_id=sso_id,
            attachment=attachment,
            updated_at=updated_at,
            creator_id=creator_id,
            owner_id=owner_id
        )

        # Add and commit to DB
        db.session.add(new_proj)
        db.session.commit()

        return redirect(url_for('all_project_list'))  # Redirect after successful insert

    # GET request - render form
    return render_template('project_form.html')

def get_db_connection():
    db_file = f"{os.path.join(BASE_DIR, 'access_control.db')}"
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row  # Optional: allows accessing columns by name
    return conn

@app.route("/projects/delete/<int:project_id>", methods=["POST"])
def delete_project(project_id):
    conn = get_db_connection()
    cur = conn.cursor()

    # Check for related kanban columns
    cur.execute("SELECT COUNT(*) FROM kanban_columns WHERE project_id = ?", (project_id,))
    count = cur.fetchone()[0]

    if count > 0:
        flash("ابتدا اطلاعات مربوط به پروژه را حذف کنید", "danger")
    else:
        cur.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
        flash("پروژه با موفقیت حذف شد", "success")

    conn.close()
    return redirect(url_for('all_project_list'))

    
# ######################################
# Tasks
# ######################################
@app.route('/project/<int:project_id>/tasks')
@login_required
def task_list(project_id):
    project = Project.query.get_or_404(project_id)
    tasks = Task.query.join(KanbanColumn).filter(KanbanColumn.project_id == project_id).all()
    return render_template('task_list.html', project=project, tasks=tasks)

# @app.route('/project/<int:project_id>/tasks/new', methods=['GET', 'POST'])
# @login_required
# def create_task(project_id):
#     project = Project.query.get_or_404(project_id)
#     if current_user.id not in [project.owner_id, project.creator_id]:
#         abort(403)

#     columns = KanbanColumn.query.filter_by(project_id=project.id).order_by(KanbanColumn.order).all()
#     column = next((c for c in columns if c.order == 1), columns[0] if columns else None)
#     if not column:
#         flash("No column found to assign task to.", "error")
#         return redirect(url_for('task_list', project_id=project_id))

#     if request.method == 'POST':
#         task = Task(
#             title=request.form['title'],
#             description=request.form['description'],
#             column_id=column.id,
#             assignee_id=request.form.get('assignee_id') or None,
#             due_date=request.form.get('due_date') or None,
#         )
#         db.session.add(task)
#         db.session.commit()
#         flash("Task created successfully.")
#         return redirect(url_for('task_list', project_id=project.id))

#     users = User.query.all()
#     return render_template('task_form.html', project=project, users=users, task=None)

@app.route('/tasks/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    task = Task.query.get_or_404(task_id)
    project = task.kanban_column.project

    # Permission checks
    is_owner = current_user.id == project.owner_id
    is_creator = current_user.id == project.creator_id
    is_column_user = current_user in task.kanban_column.users
    is_task_user = current_user in task.assigned_users

    if not (is_owner or is_creator or is_column_user or is_task_user):
        abort(403)

    columns = KanbanColumn.query.filter_by(project_id=project.id).order_by(KanbanColumn.order).all()
    users = User.query.all()

    if request.method == 'POST':
        if is_owner or is_creator:
            task.title = request.form['title']
            task.description = request.form['description']
            task.due_date = request.form.get('due_date') or None
        if is_owner or is_creator or is_column_user or is_task_user:
            task.kanban_column_id = int(request.form['kanban_column_id'])
            task.assignee_id = request.form.get('assignee_id') or None

        db.session.commit()
        flash("Task updated.")
        return redirect(url_for('task_list', project_id=project.id))

    return render_template('task_form.html', task=task, project=project, columns=columns, users=users)

@app.route('/tasks/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    project = task.kanban_column.project

    if current_user.id not in [project.owner_id, project.creator_id]:
        abort(403)

    db.session.delete(task)
    db.session.commit()
    flash("Task deleted successfully.")
    return redirect(url_for('task_list', project_id=project.id))

@app.route('/tasks/<int:task_id>/assign-users', methods=['GET', 'POST'])
# @requires_auth
@login_required  # <-- Make sure this is added
def assign_users_to_task(task_id):
    task = Task.query.get_or_404(task_id)
    project = task.column.project
    editable = (
        current_user.id in [project.owner_id, project.creator_id] or
        current_user in task.column.users
    )

    if not editable:
        abort(403)

    all_users = User.query.all()
    assigned_user_ids = [u.id for u in task.assigned_users]

    if request.method == 'POST':
        selected_user_ids = request.form.getlist('user_ids')
        task.assigned_users = User.query.filter(User.id.in_(selected_user_ids)).all()
        db.session.commit()
        flash('Users assigned to task successfully.', 'success')
        return redirect(url_for('task_list', project_id=project.id))

    return render_template('assign_users_to_task.html',
                           task=task,
                           project=project,
                           all_users=all_users,
                           assigned_user_ids=assigned_user_ids)

# ########################################
# aSSIGN USERS TO COLUMNS
# ########################################
@app.route('/projects/<int:project_id>')
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    return render_template('project_detail.html', project=project)

@app.route('/projects/<int:project_id>/columns/<int:column_id>/assign-users', methods=['GET', 'POST'])
def assign_users_to_column(project_id, column_id):
    project = Project.query.get_or_404(project_id)
    column = KanbanColumn.query.get_or_404(column_id)
    all_users = User.query.all()

    if request.method == 'POST':
        selected_user_ids = request.form.getlist('user_ids')  # List of selected user IDs from the form
        selected_user_ids = list(map(int, selected_user_ids))

        # Detach users who were previously assigned but now unchecked
        column.users = [user for user in column.users if user.id in selected_user_ids]

        # Add new users who are checked now but weren't before
        current_user_ids = {user.id for user in column.users}
        for user in all_users:
            if user.id in selected_user_ids and user.id not in current_user_ids:
                column.users.append(user)

        db.session.commit()
        flash('User assignments updated successfully.', 'success')
        return redirect(url_for('all_project_list'))

    assigned_users = column.users
    return render_template('assign_users_to_column.html',
                           project=project,
                           column=column,
                           all_users=all_users,
                           assigned_users=assigned_users)

 # ###################################
 # ###################################
 # ###################################
 
@app.route('/api/faculty_by_markaz', methods=['GET'])
def faculty_by_markaz():
    markaz_name = request.args.get('markaz')
    # logger.info("--------------")
    # logger.info(markaz_name)
    if not markaz_name:
        return jsonify({"error": "Missing markaz parameter"}), 400

    data = get_faculty_details_by_markaz(markaz_name)
    return jsonify(data)

@app.route("/debug-callback")
def debug_callback():
    """Debug route for inspecting callback parameters."""
    # logger.info("Debug callback params: %s", request.args)
    return f"Callback received, params: {request.args}"

def create_ssl_context():
    """Create and configure SSL context."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=SSL_CERT_PATH, keyfile=SSL_KEY_PATH)
    # logger.info("SSL context created successfully")
    return context

@app.before_request
def load_current_user():
    user_id = session.get('user_id')
    if user_id:
        g.current_user = db.session.get(User, user_id)
    else:
        g.current_user = None
            
    sso_id = session.get('user')
    if sso_id:
        user = User.query.filter_by(sso_id=sso_id).first()  # this fails if no context
        g.user = user
    else:
        g.user = None

@login_manager.user_loader
def load_user(user_id):
    # Use Session.get() instead of deprecated Query.get()
    return db.session.get(User, int(user_id))

@app.route('/project/<int:project_id>/kanban')
@login_required
def project_kanban(project_id):
    project = Project.query.get_or_404(project_id)
    columns = KanbanColumn.query.filter_by(project_id=project_id).order_by(KanbanColumn.position).all()
    form = TaskForm()  # make sure you have TaskForm imported

    # Get all tasks related to this project
    project_tasks = Task.query.filter_by(project_id=project_id).all()

    # Group tasks by column_id
    tasks_by_column = defaultdict(list)
    for task in project_tasks:
        tasks_by_column[task.column_id].append(task)

    # ✅ Pass the grouped tasks to the template
    return render_template(
        'kanban_board.html',
        project=project,
        columns=columns,
        form=form,
        tasks=tasks_by_column
    )



@app.route('/charts-data')
@login_required
def charts_data():
    try:
        now = dt.datetime.now()
        max_start_time = now - timedelta(days=365)  # Maximum 1 year of data
        
        # Get filters - only apply one at a time
        time_range = request.args.get('time_range')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        time_from = request.args.get('time_from', '00:00')
        time_to = request.args.get('time_to', '23:59')
        
        end_time_str = None
        
        # Priority: custom date range > time_range
        # If custom date range is provided, ignore time_range
        if date_from and date_to:
            # Custom date range
            try:
                # Parse Persian calendar date (format: YYYY/MM/DD)
                from_date_parts = list(map(int, date_from.split('/')))
                to_date_parts = list(map(int, date_to.split('/')))
                
                # Parse time (format: HH:MM)
                time_from_parts = list(map(int, time_from.split(':')))
                time_to_parts = list(map(int, time_to.split(':')))
                
                # Create jdatetime objects
                start_jd = jdatetime.datetime(
                    from_date_parts[0], from_date_parts[1], from_date_parts[2],
                    time_from_parts[0], time_from_parts[1]
                )
                end_jd = jdatetime.datetime(
                    to_date_parts[0], to_date_parts[1], to_date_parts[2],
                    time_to_parts[0], time_to_parts[1]
                )
                
                # Convert to Gregorian datetime
                start_time = start_jd.togregorian()
                end_time = end_jd.togregorian()
                
                # Ensure we're working with Tehran timezone
                tehran_tz = pytz.timezone('Asia/Tehran')
                if start_time.tzinfo is None:
                    start_time = tehran_tz.localize(start_time)
                if end_time.tzinfo is None:
                    end_time = tehran_tz.localize(end_time)
                
                # Convert to naive datetime for SQLite
                start_time = start_time.replace(tzinfo=None)
                end_time = end_time.replace(tzinfo=None)
                
                # Add 1 second to end_time to include the entire end day (23:59:59)
                # This ensures we capture all data for the end date
                end_time = end_time + timedelta(seconds=1)
                
                # Ensure not more than 1 year
                if start_time < max_start_time:
                    start_time = max_start_time
                
                start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
                end_time_str = end_time.strftime('%Y-%m-%d %H:%M:%S')
                
            except (ValueError, IndexError, AttributeError) as e:
                logging.error(f"Error parsing custom date range: {e}")
                # Fallback to default 1 year
                start_time_str = max_start_time.strftime('%Y-%m-%d %H:%M:%S')
                end_time_str = None
        elif time_range:
            # Predefined time range (only if custom range is not provided)
            if time_range == '1h':
                start_time = now - timedelta(hours=1)
            elif time_range == '3h':
                start_time = now - timedelta(hours=3)
            elif time_range == '6h':
                start_time = now - timedelta(hours=6)
            elif time_range == '12h':
                start_time = now - timedelta(hours=12)
            elif time_range == '1d':
                start_time = now - timedelta(days=1)
            elif time_range == '1w':
                start_time = now - timedelta(weeks=1)
            elif time_range == '1m':
                start_time = now - timedelta(days=30)
            elif time_range == '1y':
                start_time = now - timedelta(days=365)
            else:
                start_time = max_start_time  # default to 1 year

            # Ensure not more than 1 year
            if start_time < max_start_time:
                start_time = max_start_time
            
            start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
        else:
            # No filter, use default 1 year
            start_time_str = max_start_time.strftime('%Y-%m-%d %H:%M:%S')

        DB_PATH2 = "C:\\services\\cert2\\app\\fetch_data\\faculty_data.db"
        try:
            conn = sqlite3.connect(DB_PATH2)
            cursor = conn.cursor()

            # === 1. Get all relevant rows ===
            # Optimize query for large date ranges - limit results to prevent timeout
            try:
                if end_time_str:
                    # Custom range with both start and end
                    # Use < instead of <= to include all data up to (but not including) end_time
                    # Since we added 1 second to end_time, this will include all data for the end date
                    query = """
                        SELECT url, timestamp, key, value
                        FROM monitor_data
                        WHERE datetime(timestamp) >= datetime(?) AND datetime(timestamp) < datetime(?)
                        ORDER BY url, timestamp ASC
                        LIMIT 50000
                    """
                    cursor.execute(query, (start_time_str, end_time_str))
                else:
                    # Only start time (predefined ranges or default)
                    # Limit results for large ranges to prevent timeout
                    query = """
                        SELECT url, timestamp, key, value
                        FROM monitor_data
                        WHERE datetime(timestamp) >= datetime(?)
                        ORDER BY url, timestamp ASC
                        LIMIT 50000
                    """
                    cursor.execute(query, (start_time_str,))
                
                rows = cursor.fetchall()
            except Exception as e:
                logging.error(f"Error executing query: {e}", exc_info=True)
                rows = []
            finally:
                conn.close()
        except Exception as e:
            logging.error(f"Error connecting to database: {e}", exc_info=True)
            rows = []

        charts = {}
        zones = {
            "Zone1": "تهران، شهرستانهای تهران و البرز",
            "Zone2": "گیلان، مازندران و گلستان",
            "Zone3": "آذربایجان شرقی، آذربایجان غربی، اردبیل و زنجان",
            "Zone4": "قم، قزوین، مرکزی و همدان",
            "Zone5": "ایلام، کردستان، کرمانشاه و لرستان",
            "Zone6": "اصفهان، چهارمحال و بختیاری و یزد",
            "Zone7": "کهگیلویه و بویراحمد و فارس",
            "Zone8": "سیستان و بلوچستان، کرمان، هرمزگان",
            "Zone9": "خراسان رضوی، جنوبی و شمالی و سمنان",
            "Zone10": "بوشهر و خوزستان",
            "Zone11": "سامانه جلسات"
            }
        chartlabels = {
            "online_lms_user": "کاربران آنلاین LMS",
            "online_adobe_class": "کلاس های درحال ضبط Adobe",
            "online_adobe_user": "کاربران Adobe",
            "online_quizes": "آزمونهای درحال برگزاری",
            "online_users_in_quizes": "کاربران درحال برگزاری آزمون",
            }        
        if rows:
            # === 2. Group data by URL and key ===
            url_data = {}
            for url, timestamp, key, value in rows:
                if url not in url_data:
                    url_data[url] = {}
                if key not in url_data[url]:
                    url_data[url][key] = {"timestamps": [], "values": []}

                # Convert to Jalali date string
                try:
                    ts = timestamp
                    if isinstance(ts, str):
                        # Try different datetime parsing formats
                        try:
                            ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        except ValueError:
                            try:
                                ts = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
                            except ValueError:
                                ts = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S.%f')
                    
                    # Convert to naive datetime if it has timezone info
                    if hasattr(ts, 'tzinfo') and ts.tzinfo is not None:
                        ts = ts.replace(tzinfo=None)
                    
                    jalali_ts = jdatetime.datetime.fromgregorian(datetime=ts).strftime("%Y/%m/%d %H:%M")
                    url_data[url][key]["timestamps"].append(jalali_ts)
                    url_data[url][key]["values"].append(value)
                except Exception as e:
                    logging.error(f"Error processing timestamp {timestamp} for {url}/{key}: {e}")
                    # Skip this row if timestamp parsing fails
                    continue

            # === 3. Build Chart.js structure for each URL ===
            # فقط Zone1 تا Zone11 را پردازش می‌کنیم (11 منطقه)
            zone_order = ["Zone1", "Zone2", "Zone3", "Zone4", "Zone5", "Zone6", 
                         "Zone7", "Zone8", "Zone9", "Zone10", "Zone11"]
            
            for url in zone_order:
                if url not in url_data:
                    continue
                    
                keys = url_data[url]
                datasets = []
                labels = []  # we can take timestamps from first key
                first_key = next(iter(keys))
                labels = keys[first_key]["timestamps"]

                for key, data in keys.items():
                    label = chartlabels.get(key, key)  # Use key as fallback if label not found
                    datasets.append({
                        "label": label,
                        "data": data["values"],
                        "borderColor": get_color_for_key(key),
                        "backgroundColor": get_color_for_key(key),
                        "fill": False
                    })
                    for lms_user_count in data["values"]:
                        if int(lms_user_count) >= 1500:
                            token = get_sms_token()
                            send_sms(
                                token,
                                f"LMS User Countt Alert! {label}: {int(lms_user_count)}",
                                ["09123880167"]
                            )
                            break  # stop after first alert

                charts[url] = {
                    "labels": labels,
                    "datasets": datasets,
                    "title": zones.get(url, url)  # Use url as fallback if zone not found
                }

        return jsonify(charts)
    except Exception as e:
        logging.error(f"Error in charts_data endpoint: {e}", exc_info=True)
        return jsonify({
            "error": "خطا در دریافت داده‌ها",
            "message": str(e)
        }), 500

@app.route('/sync-lms-now')
@login_required
def sync_lms_now():
    """Manual LMS sync endpoint - stops continuous sync, performs manual sync, then restarts continuous sync if enabled"""
    try:
        from admin.sync_handlers import run_lms_sync
        from admin_models import DataSync
        
        logger.info("Manual LMS sync triggered by user")
        
        # Get LMS sync configuration
        sync = DataSync.query.filter_by(data_source='lms').first()
        if not sync:
            return jsonify({
                "success": False,
                "message": "پیکربندی همگام‌سازی LMS یافت نشد"
            }), 404
        
        # Run manual sync (will stop continuous sync, perform sync, then restart if enabled)
        success, records_count, error_message = run_lms_sync(
            user_id=current_user.id,
            sync_id=sync.id,
            manual_sync=True
        )
        
        if success:
            return jsonify({
                "success": True,
                "message": f"همگام‌سازی با موفقیت انجام شد. {records_count} رکورد ثبت شد.",
                "records_count": records_count
            })
        else:
            return jsonify({
                "success": False,
                "message": error_message or "خطا در همگام‌سازی داده‌ها"
            }), 500
    except Exception as e:
        logger.error(f"Error in manual LMS sync: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "message": f"خطا: {str(e)}"
        }), 500

@app.route('/tables-data')
@login_required
def tables_data():
    DB_PATH2 = "C:\\services\\cert2\\app\\fetch_data\\faculty_data.db"
    conn = sqlite3.connect(DB_PATH2)
    cursor = conn.cursor()

    # === 1. Get all relevant rows ===
    query = """
        SELECT url, timestamp, key, value
        FROM monitor_data
        ORDER BY url, timestamp ASC
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    charts = {}
    latest_values = {}
    latest_zone_resources = {}
    overall_sum = {}
    SERVICE_URL = "http://127.0.0.1:6000/metrics"
    zones = {
        "Zone1": "تهران، شهرستانهای تهران و البرز",
        "Zone2": "گیلان، مازندران و گلستان",
        "Zone3": "آذربایجان شرقی، آذربایجان غربی، اردبیل و زنجان",
        "Zone4": "قم، قزوین، مرکزی و همدان",
        "Zone5": "ایلام، کردستان، کرمانشاه و لرستان",
        "Zone6": "اصفهان، چهارمحال و بختیاری و یزد",
        "Zone7": "کهگیلویه و بویراحمد و فارس",
        "Zone8": "سیستان و بلوچستان، کرمان، هرمزگان",
        "Zone9": "خراسان رضوی، جنوبی و شمالی و سمنان",
        "Zone10": "بوشهر و خوزستان",
        "Zone11": "سامانه جلسات"
        }
    hostnames = {
        "Zone1": "lms1",
        "Zone2": "lms2",
        "Zone3": "lms3",
        "Zone4": "lms4",
        "Zone5": "lms5",
        "Zone6": "lms6",
        "Zone7": "lms7",
        "Zone8": "lms8",
        "Zone9": "lms9",
        "Zone10": "lms10",
        "Zone11": "meeting"
        }        
        
    chartlabels = {
        "online_lms_user": "کاربران آنلاین LMS",
        "online_adobe_class": "کلاس های درحال ضبط Adobe",
        "online_adobe_user": "کاربران Adobe",
        "online_quizes": "آزمونهای درحال برگزاری",
        "online_users_in_quizes": "کاربران درحال برگزاری آزمون",
        }        
    if rows:
        # === 2. Group data by URL and key ===
        url_data = {}
        for url, timestamp, key, value in rows:
            if url not in url_data:
                url_data[url] = {}
            if key not in url_data[url]:
                url_data[url][key] = {"timestamps": [], "values": []}

            # Convert to Jalali date string
            ts = timestamp
            if isinstance(ts, str):
                from datetime import datetime
                ts = datetime.fromisoformat(ts)
            jalali_ts = jdatetime.datetime.fromgregorian(datetime=ts).strftime("%Y/%m/%d %H:%M")
           
            url_data[url][key]["timestamps"].append(jalali_ts)
            url_data[url][key]["values"].append(value)

        # === 3. Build Chart.js structure for each URL ===
        # فقط Zone1 تا Zone11 را پردازش می‌کنیم (11 منطقه)
        zone_order = ["Zone1", "Zone2", "Zone3", "Zone4", "Zone5", "Zone6", 
                     "Zone7", "Zone8", "Zone9", "Zone10", "Zone11"]
        
        for url in zone_order:
            if url not in url_data:
                continue
                
            keys = url_data[url]
            datasets = []
            labels = []  # we can take timestamps from first key
            first_key = next(iter(keys))
            labels = keys[first_key]["timestamps"]
            latest_values[url] = {}
            latest_zone_resources[url] = {}

            hostname = hostnames.get(url)
            if hostname:
                print(hostname)
                response = requests.get(SERVICE_URL, params={"host": hostname})
                if response.status_code == 200:
                    # print("Metrics:", response.json())
                    latest_zone_resources[url] = response.json()
                else:
                    print("Error:", response.text)   
            
            for key, data in keys.items():
                datasets.append({
                    "label": chartlabels.get(key, key),
                    "data": data["values"],
                    "borderColor": get_color_for_key(key),
                    "backgroundColor": get_color_for_key(key),
                    "fill": False
                })
                # latest value = last entry
                latest_val = data["values"][-1]
                latest_values[url][key] = latest_val

                # update overall sum
                overall_sum[key] = overall_sum.get(key, 0) + latest_val

            charts[url] = {
                "labels": labels,
                "datasets": datasets,
                "latest_values": latest_values[url],         # fixed: return per-url latest_values
                "latest_zone_resources": latest_zone_resources[url],
                "title": zones.get(url, url)
            }

    return jsonify({
        "charts": charts,
        "overall_sum": overall_sum,
        "latest_values": latest_values,
        "latest_zone_resources": latest_zone_resources,
        "chartlabels": chartlabels
    })


def kill_process_on_port(port=5000):
    """Kill any process running on the specified port"""
    try:
        system = platform.system()
        
        if system == "Windows":
            # Windows: Use netstat to find PID, then taskkill to kill it
            try:
                # Find process using the port
                result = subprocess.run(
                    ['netstat', '-ano'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode == 0:
                    lines = result.stdout.split('\n')
                    pids_to_kill = set()
                    
                    for line in lines:
                        if f':{port}' in line and 'LISTENING' in line:
                            parts = line.split()
                            if len(parts) >= 5:
                                pid = parts[-1]
                                try:
                                    pids_to_kill.add(int(pid))
                                except ValueError:
                                    pass
                    
                    # Kill all processes found
                    for pid in pids_to_kill:
                        try:
                            logger.info(f"Killing process {pid} on port {port}")
                            subprocess.run(
                                ['taskkill', '/PID', str(pid), '/F'],
                                capture_output=True,
                                timeout=5
                            )
                            logger.info(f"Successfully killed process {pid}")
                        except subprocess.TimeoutExpired:
                            logger.warning(f"Timeout while killing process {pid}")
                        except Exception as e:
                            logger.warning(f"Error killing process {pid}: {e}")
                    
                    if pids_to_kill:
                        # Wait a bit for port to be released
                        time.sleep(1)
                        logger.info(f"Freed port {port}")
                    else:
                        logger.info(f"No process found on port {port}")
                else:
                    logger.warning(f"Failed to run netstat: {result.stderr}")
            except subprocess.TimeoutExpired:
                logger.warning("Timeout while checking for processes on port")
            except FileNotFoundError:
                logger.warning("netstat or taskkill not found - skipping port cleanup")
            except Exception as e:
                logger.warning(f"Error checking/killing processes on port {port}: {e}")
        
        elif system in ["Linux", "Darwin"]:  # Linux or macOS
            try:
                # Use lsof to find process using the port
                result = subprocess.run(
                    ['lsof', '-ti', f':{port}'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode == 0 and result.stdout.strip():
                    pids = result.stdout.strip().split('\n')
                    for pid in pids:
                        try:
                            logger.info(f"Killing process {pid} on port {port}")
                            subprocess.run(
                                ['kill', '-9', pid],
                                capture_output=True,
                                timeout=5
                            )
                            logger.info(f"Successfully killed process {pid}")
                        except subprocess.TimeoutExpired:
                            logger.warning(f"Timeout while killing process {pid}")
                        except Exception as e:
                            logger.warning(f"Error killing process {pid}: {e}")
                    
                    if pids:
                        time.sleep(1)
                        logger.info(f"Freed port {port}")
                else:
                    logger.info(f"No process found on port {port}")
            except subprocess.TimeoutExpired:
                logger.warning("Timeout while checking for processes on port")
            except FileNotFoundError:
                logger.warning("lsof not found - skipping port cleanup")
            except Exception as e:
                logger.warning(f"Error checking/killing processes on port {port}: {e}")
        else:
            logger.warning(f"Unsupported platform: {system} - skipping port cleanup")
            
    except Exception as e:
        logger.error(f"Unexpected error in kill_process_on_port: {e}")


if __name__ == "__main__":
    # Kill any existing processes on port 5000 before starting
    logger.info("Checking for processes on port 5000...")
    kill_process_on_port(5000)
    
    with app.app_context():
        # db.create_all()
        serve(app, host="0.0.0.0", port=5000)
