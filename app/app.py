import os
import requests
import logging
import secrets
import ssl
import sqlite3
from urllib.parse import quote_plus
from flask import Flask, redirect, url_for, session, request, render_template, jsonify, flash, abort
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
# app.register_blueprint(dashboard_bp)  # Legacy routes - DISABLED (using new architecture)

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

    if stored_state != returned_state:
        logger.error("CSRF Warning: State mismatch")
        return render_template("error.html", error="Authorization error: CSRF Warning!"), 400

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
            if access_level in ["staff"]:
                admin_access = AccessLevel(level="admin", user_id=user.id)
                db.session.add(admin_access)
                db.session.commit()
                is_admin = True
        
        # NEW: Tell Flask-Login to log the user in
        login_user(user)

        g.current_user = user

        # Check access: user must be admin and have staff usertype
        if is_admin and access_level in ["staff"]:
            return render_template("tools.html", user_info=userinfo)
            # return redirect(url_for("dashboard.dashboard_list"))
        else:
            # return render_template("profile.html", user=userinfo)
            SSO_LOGOUT_URL = "https://sso.cfu.ac.ir/logout?service=https://bi.cfu.ac.ir"
            return redirect(SSO_LOGOUT_URL)

        return redirect("https://sso.cfu.ac.ir/logout?service=https://bi.cfu.ac.ir")
        # return render_template("profile.html", user=userinfo)

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
    """Log out the user."""
    session.clear()
    logger.info("User logged out, session cleared.")
    return redirect("https://sso.cfu.ac.ir/logout?service=https://bi.cfu.ac.ir")


@app.route('/tools')
def list_tools():
    user_info = session.get("user_info")
    return render_template("tools.html", user_info=user_info)

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
    return User.query.get(int(user_id))

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
    time_range = request.args.get('time_range', '1h')
    now = dt.datetime.now()

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
        start_time = now - timedelta(hours=1)  # default

    # Convert datetime to ISO format string for SQLite
    # SQLite stores datetime as TEXT, format: 'YYYY-MM-DD HH:MM:SS.ffffff'
    # Use strftime to ensure consistent format for comparison
    start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')

    DB_PATH2 = "C:\\services\\cert2\\app\\fetch_data\\faculty_data.db"
    conn = sqlite3.connect(DB_PATH2)
    cursor = conn.cursor()

    # === 1. Get all relevant rows ===
    # SQLite datetime comparison - ensure both sides are in same format
    query = """
        SELECT url, timestamp, key, value
        FROM monitor_data
        WHERE datetime(timestamp) >= datetime(?)
        ORDER BY url, timestamp ASC
    """
    cursor.execute(query, (start_time_str,))
    rows = cursor.fetchall()
    conn.close()

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
        "Zone11": "سامانه جلسات",
        "meeting": "سامانه جلسات"
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
        for url, keys in url_data.items():
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
                    if int(lms_user_count) >= 200:
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
        "Zone1": "تهران و البرز",
        "Zone2": "گیلان، مازندران و گلستان",
        "Zone3": "آذربایجان، اردبیل و زنجان",
        "Zone4": "قم، قزوین، مرکزی و همران",
        "Zone5": "ایلام، کردستان و کرمانشاه",
        "Zone6": "اصفهان، چهارمحال و بختیاری و یزد",
        "Zone7": "کهگیلویه و بویراحمد و فارس",
        "Zone8": "سیستان و بلوچستان، کرمان، هرمزگان",
        "Zone9": "خراسان و سمنان",
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
        for url, keys in url_data.items():
            datasets = []
            labels = []  # we can take timestamps from first key
            first_key = next(iter(keys))
            labels = keys[first_key]["timestamps"]
            latest_values[url] = []
            latest_zone_resources[url] = []

            hostname = hostnames[url]
            print(hostname)
            response = requests.get(SERVICE_URL, params={"host": hostname})
            if response.status_code == 200:
                # print("Metrics:", response.json())
                latest_zone_resources[url] = response.json()
            else:
                print("Error:", response.text)   
            for key, data in keys.items():
                datasets.append({
                    "label": chartlabels[key],
                    "data": data["values"],
                    "borderColor": get_color_for_key(key),
                    "backgroundColor": get_color_for_key(key),
                    "fill": False
                })
                # latest value = last entry
                latest_val = data["values"][-1]
                latest_values[url].append({key: latest_val})

                # update overall sum
                overall_sum[key] = overall_sum.get(key, 0) + latest_val


            charts[url] = {
                "labels": labels,
                "datasets": datasets,
                "latest_values": latest_values[url],         # fixed: return per-url latest_values
                "latest_zone_resources": latest_zone_resources[url],
                "title": zones[url]
            }

    return jsonify({
        "charts": charts,
        "overall_sum": overall_sum
    })


if __name__ == "__main__":
    with app.app_context():
        # db.create_all()
        serve(app, host="0.0.0.0", port=5000)
