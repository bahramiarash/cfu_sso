import os
import sys
import logging
import socket
from flask import Flask, render_template, request, redirect, url_for, Response, jsonify
from dotenv import load_dotenv

# Add shared directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from utils.auth_client import AuthClient

# Load environment variables
BASE_DIR_ENV = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR_ENV))
load_dotenv(dotenv_path=os.path.join(PROJECT_ROOT, '.env'))
load_dotenv()

# Configure logging first (needed for normalization logging)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Get AUTH_SERVICE_URL from environment
# For Docker: use http://auth-service:5001
# For direct execution: use http://localhost:5001
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:5001")

# Normalize AUTH_SERVICE_URL - replace Docker hostnames with localhost if not in Docker
# Check if we're running in Docker by checking if auth-service hostname resolves
IN_DOCKER = False
try:
    socket.gethostbyname('auth-service')
    # If we can resolve auth-service, we're in Docker - keep it
    IN_DOCKER = True
    logger.info("Running in Docker - using auth-service hostname")
except socket.gaierror:
    # If we can't resolve auth-service, we're not in Docker - use localhost
    if 'auth-service' in AUTH_SERVICE_URL:
        AUTH_SERVICE_URL = AUTH_SERVICE_URL.replace('auth-service', 'localhost')
        logger.info(f"Not in Docker - changed AUTH_SERVICE_URL to: {AUTH_SERVICE_URL}")

# Set MONOLITHIC_APP_URL based on environment
# In Docker, we might need a different hostname, but for now it runs on localhost:5006
# The monolithic app typically runs on the same host as gateway service
MONOLITHIC_APP_URL = os.getenv("MONOLITHIC_APP_URL") or "http://localhost:5006"

# Initialize Flask app
# IMPORTANT: static_folder=None disables Flask's default /static/ route
# We handle static files manually via our custom route
app = Flask(__name__, template_folder='templates', static_folder=None)

# Initialize auth client
auth_client = AuthClient(AUTH_SERVICE_URL)

def get_auth_token():
    """Extract JWT token from request"""
    auth_header = request.headers.get("Authorization") or ""
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.replace("Bearer ", "")
    return request.cookies.get("auth_token")

# CRITICAL: Static files route must be defined early to match before other routes
# Flask's default /static/ route is disabled (static_folder=None), so this route handles all /static/ requests
@app.route("/static/<path:filename>")
def static_files(filename):
    """Serve static files directly from file system or proxy from monolithic app"""
    import requests
    import os
    from flask import send_file
    
    logger.info(f"=== STATIC FILE REQUEST: {filename} ===")
    
    # Try to serve directly from file system first (more efficient)
    # Calculate path: from gateway-service/app.py -> services -> cert2 -> app -> static
    current_file = os.path.abspath(__file__)
    # Go up: gateway-service/app.py -> gateway-service -> services -> cert2
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    static_dir = os.path.join(project_root, "app", "static")
    file_path = os.path.join(static_dir, filename)
    
    logger.info(f"Serving static file: {filename}, static_dir: {static_dir}, file_path: {file_path}, exists: {os.path.exists(file_path)}")
    
    # Check if file exists in file system
    if os.path.exists(file_path) and os.path.isfile(file_path):
        try:
            # Use send_file instead of send_from_directory for more control
            response = send_file(file_path)
            response.headers['Cache-Control'] = 'public, max-age=31536000'  # 1 year
            logger.info(f"✓ Served static file from file system: {filename}")
            return response
        except Exception as e:
            logger.error(f"✗ Error serving static file from file system {filename}: {e}", exc_info=True)
    else:
        logger.warning(f"✗ Static file not found in file system: {file_path}")
    
    # Fallback: Proxy from monolithic app
    target_url = f"{MONOLITHIC_APP_URL}/static/{filename}"
    logger.info(f"Proxying static file to monolithic app: {target_url}")
    
    try:
        # Forward request to monolithic app
        resp = requests.get(target_url, timeout=10, allow_redirects=False)
        logger.info(f"Monolithic app response for {filename}: status={resp.status_code}")
        
        if resp.status_code == 200:
            # Return response with proper headers
            from flask import Response
            response = Response(resp.content, status=resp.status_code)
            
            # Copy content type and other headers
            if 'Content-Type' in resp.headers:
                response.headers['Content-Type'] = resp.headers['Content-Type']
            if 'Content-Length' in resp.headers:
                response.headers['Content-Length'] = resp.headers['Content-Length']
            
            # Cache static files
            response.headers['Cache-Control'] = 'public, max-age=31536000'  # 1 year
            logger.info(f"✓ Proxied static file from monolithic app: {filename}")
            return response
        else:
            logger.warning(f"✗ Monolithic app returned {resp.status_code} for {filename}")
            return {"error": "Static file not found"}, 404
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Error proxying static file {filename} to {target_url}: {e}", exc_info=True)
        return {"error": "Static file not found"}, 404

@app.route("/")
def index():
    """Main page - redirects to tools page"""
    token = get_auth_token()
    logger.info(f"Request to / - cookies: {list(request.cookies.keys())}, token: {'present' if token else 'missing'}")
    if not token:
        # Redirect to /auth/login (which will be proxied to Auth Service)
        redirect_uri = request.url_root.rstrip('/')
        logger.info(f"No token found, redirecting to /auth/login")
        return redirect(f"/auth/login?redirect_uri={redirect_uri}")
    
    # Validate token
    logger.info(f"Validating token: {token[:20]}...")
    result = auth_client.validate_token(token)
    if "error" in result:
        logger.warning(f"Token validation failed: {result.get('error')}")
        redirect_uri = request.url_root.rstrip('/')
        return redirect(f"/auth/login?redirect_uri={redirect_uri}")
    
    user = result.get("user", {})
    logger.info(f"Token validated successfully for user: {user.get('username', 'unknown')}")
    
    # Redirect to /tools page (similar to monolithic app)
    return redirect("/tools")

@app.route("/login")
def login_redirect():
    """Redirect /login to /auth/login (for compatibility with Auth Service redirects)"""
    redirect_uri = request.args.get("next", request.args.get("redirect_uri", request.url_root.rstrip('/')))
    return redirect(f"/auth/login?redirect_uri={redirect_uri}")

@app.route("/tools")
def tools():
    """Main tools page - similar to monolithic app"""
    token = get_auth_token()
    if not token:
        redirect_uri = request.url_root.rstrip('/')
        return redirect(f"/auth/login?redirect_uri={redirect_uri}")
    
    # Validate token
    result = auth_client.validate_token(token)
    if "error" in result:
        redirect_uri = request.url_root.rstrip('/')
        return redirect(f"/auth/login?redirect_uri={redirect_uri}")
    
    user_info = result.get("user", {})
    
    # Check if user has dashboard access (simplified - can be enhanced later)
    has_dashboard_access = True  # For now, assume all authenticated users have access
    
    # Check if user is survey manager (simplified - can be enhanced later)
    is_survey_manager = False  # Can be checked from user_info or database later
    
    # Render tools page
    return render_template('tools.html', 
                         user_info=user_info,
                         has_dashboard_access=has_dashboard_access,
                         is_survey_manager=is_survey_manager)

@app.route("/survey", defaults={"path": ""}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
@app.route("/survey/", defaults={"path": ""}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
@app.route("/survey/<path:path>", methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
def survey_proxy(path):
    """Proxy survey requests to Survey Service or monolithic app"""
    import requests
    
    token = get_auth_token()
    if not token:
        redirect_uri = request.url_root.rstrip('/')
        return redirect(f"/auth/login?redirect_uri={redirect_uri}")
    
    # For now, proxy to monolithic app (Survey Service only has API endpoints, no HTML)
    # Monolithic app runs on port 5006 to avoid conflict with Gateway Service (port 5000)
    # MONOLITHIC_APP_URL is set at module level
    
    # Build target URL - ensure MONOLITHIC_APP_URL is set
    if not MONOLITHIC_APP_URL:
        logger.error("MONOLITHIC_APP_URL is not set")
        return "Error: MONOLITHIC_APP_URL is not configured", 500
    
    if path:
        target_url = f"{MONOLITHIC_APP_URL}/survey/{path}"
    else:
        target_url = f"{MONOLITHIC_APP_URL}/survey"
    
    # Add query string if present
    if request.query_string:
        target_url += f"?{request.query_string.decode()}"
    
    logger.info(f"Proxying survey request to: {target_url}")
    
    try:
        # Forward request with cookies and headers
        # Monolithic app uses Flask session, so we need to forward all cookies
        headers = {
            "Authorization": f"Bearer {token}",
        }
        
        # CRITICAL: Add auth_token to headers so monolithic app can sync session
        # This ensures auth_token is available even if cookies don't work
        if token:
            headers["X-Auth-Token"] = token
        
        # Create a session to maintain cookies
        session_obj = requests.Session()
        
        # Forward all cookies from the original request to maintain session
        for name, value in request.cookies.items():
            session_obj.cookies.set(name, value, path='/')
        
        # Also set auth_token cookie if we have it (for session sync in monolithic app)
        if token:
            session_obj.cookies.set("auth_token", token, path='/')
        
        # Forward the request (don't follow redirects automatically)
        # Handle different HTTP methods
        request_kwargs = {
            'headers': headers,
            'allow_redirects': False,
            'timeout': 30
        }
        
        if request.method == "GET":
            resp = session_obj.get(target_url, **request_kwargs)
        elif request.method == "POST":
            # Handle both form data and JSON
            if request.is_json:
                request_kwargs['json'] = request.json
            else:
                request_kwargs['data'] = request.form
                if request.files:
                    request_kwargs['files'] = request.files
            resp = session_obj.post(target_url, **request_kwargs)
        elif request.method in ["PUT", "PATCH"]:
            # Handle both form data and JSON
            if request.is_json:
                request_kwargs['json'] = request.json
            else:
                request_kwargs['data'] = request.form
                if request.files:
                    request_kwargs['files'] = request.files
            resp = session_obj.request(request.method, target_url, **request_kwargs)
        elif request.method == "DELETE":
            resp = session_obj.delete(target_url, **request_kwargs)
        else:
            # For other methods (OPTIONS, HEAD, etc.)
            resp = session_obj.request(request.method, target_url, **request_kwargs)
        
        # Handle redirects - convert monolithic app URLs to gateway URLs
        if resp.status_code in [301, 302, 303, 307, 308]:
            location = resp.headers.get('Location') or ''
            logger.info(f"Survey redirect detected: {location}")
            
            # Ensure location is a string
            if location is None:
                location = ''
            
            # Parse the location URL
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(location)
            new_path = None
            
            # Handle both absolute URLs (with localhost:5006) and relative URLs
            if location and ('localhost:5006' in location or '127.0.0.1:5006' in location):
                # Absolute URL with localhost:5006 - extract path and query
                new_path = parsed.path or '/'
                if parsed.query:
                    new_path += f"?{parsed.query}"
            elif location and location.startswith('/'):
                # Relative URL - use as is
                new_path = location
            elif location:
                # Other absolute URL (e.g., https://...) - keep as is unless it's SSO
                if 'sso.cfu.ac.ir' in location:
                    # Keep SSO redirects as is
                    redirect_response = redirect(location)
                    for cookie in session_obj.cookies:
                        redirect_response.set_cookie(
                            cookie.name, cookie.value,
                            domain=None, path=cookie.path if cookie.path else '/',
                            secure=False, httponly=True, samesite='Lax'
                        )
                    return redirect_response
                else:
                    # Unknown absolute URL - use path only
                    new_path = parsed.path or '/'
                    if parsed.query:
                        new_path += f"?{parsed.query}"
            else:
                # Empty location - default to root
                new_path = '/'
            
            # Ensure new_path is set and is a string
            if new_path is None:
                new_path = '/'
            
            # Convert /login to /auth/login (gateway auth route)
            if new_path == '/login' or (new_path and new_path.startswith('/login?')):
                new_path = new_path.replace('/login', '/auth/login', 1)
                logger.info(f"Converted /login redirect to: {new_path}")
            
            # Return redirect through gateway
            redirect_response = redirect(new_path)
            
            # Copy cookies from monolithic app response
            for cookie in session_obj.cookies:
                redirect_response.set_cookie(
                    cookie.name,
                    cookie.value,
                    domain=None,
                    path=cookie.path if cookie.path else '/',
                    secure=False,  # Will be set by nginx if HTTPS
                    httponly=True,
                    samesite='Lax'
                )
            
            return redirect_response
        
        # Return response
        from flask import Response
        response = Response(resp.content, status=resp.status_code)
        
        # Copy response headers (except Location which we handle above)
        for key, value in resp.headers.items():
            if key.lower() not in ['content-encoding', 'transfer-encoding', 'connection', 'location']:
                response.headers[key] = value
        
        # Copy cookies from monolithic app response
        for cookie in session_obj.cookies:
            response.set_cookie(
                cookie.name,
                cookie.value,
                domain=None,
                path=cookie.path if cookie.path else '/',
                secure=False,
                httponly=True,
                samesite='Lax'
            )
        
        return response
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Error proxying survey request: Cannot connect to monolithic app at {MONOLITHIC_APP_URL}")
        logger.error(f"Make sure the monolithic app is running. Start it with: python start-monolithic-app.ps1")
        error_msg = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>سرویس در دسترس نیست</title>
    <style>
        body {{ font-family: Tahoma, Arial, sans-serif; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 600px; margin: 50px auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #d32f2f; }}
        code {{ background: #f5f5f5; padding: 2px 6px; border-radius: 3px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>سرویس در دسترس نیست</h1>
        <p>سرویس نظرسنجی در حال حاضر در دسترس نیست. لطفاً با مدیر سیستم تماس بگیرید.</p>
        <p><small>جزئیات خطا: {str(e)}</small></p>
    </div>
</body>
</html>"""
        from flask import make_response
        response = make_response(error_msg, 503)
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        return response
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Error proxying survey request: {e}", exc_info=True)
        logger.error(f"Full traceback: {error_traceback}")
        return f"Error connecting to survey service: {str(e)}", 500

@app.route("/charts-data", methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
def charts_data_proxy():
    """Proxy charts-data requests to monolithic app"""
    import requests
    
    token = get_auth_token()
    if not token:
        redirect_uri = request.url_root.rstrip('/')
        return redirect(f"/auth/login?redirect_uri={redirect_uri}")
    
    # Build target URL
    target_url = f"{MONOLITHIC_APP_URL}/charts-data"
    
    # Add query string if present
    if request.query_string:
        target_url += f"?{request.query_string.decode()}"
    
    logger.info(f"Proxying charts-data request to: {target_url}")
    
    try:
        # Forward request with cookies and headers
        headers = {
            "Authorization": f"Bearer {token}",
        }
        
        if token:
            headers["X-Auth-Token"] = token
        
        # Create a session to maintain cookies
        session_obj = requests.Session()
        
        # Forward all cookies from the original request
        for name, value in request.cookies.items():
            session_obj.cookies.set(name, value, path='/')
        
        if token:
            session_obj.cookies.set("auth_token", token, path='/')
        
        # Forward the request
        request_kwargs = {
            'headers': headers,
            'allow_redirects': False,
            'timeout': 120
        }
        
        if request.method == "GET":
            resp = session_obj.get(target_url, **request_kwargs)
        elif request.method == "POST":
            if request.is_json:
                request_kwargs['json'] = request.json
            else:
                request_kwargs['data'] = request.form
            resp = session_obj.post(target_url, **request_kwargs)
        else:
            resp = session_obj.request(request.method, target_url, **request_kwargs)
        
        # Return response
        from flask import Response
        response = Response(resp.content, status=resp.status_code)
        
        # Copy response headers
        for key, value in resp.headers.items():
            if key.lower() not in ['content-encoding', 'transfer-encoding', 'connection']:
                response.headers[key] = value
        
        # Copy cookies
        for cookie in session_obj.cookies:
            response.set_cookie(
                cookie.name,
                cookie.value,
                domain=None,
                path=cookie.path if cookie.path else '/',
                secure=False,
                httponly=True,
                samesite='Lax'
            )
        
        return response
    except Exception as e:
        logger.error(f"Error proxying charts-data request: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/tables-data", methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
def tables_data_proxy():
    """Proxy tables-data requests to monolithic app"""
    import requests
    
    token = get_auth_token()
    if not token:
        redirect_uri = request.url_root.rstrip('/')
        return redirect(f"/auth/login?redirect_uri={redirect_uri}")
    
    # Build target URL
    target_url = f"{MONOLITHIC_APP_URL}/tables-data"
    
    # Add query string if present
    if request.query_string:
        target_url += f"?{request.query_string.decode()}"
    
    logger.info(f"Proxying tables-data request to: {target_url}")
    
    try:
        # Forward request with cookies and headers
        headers = {
            "Authorization": f"Bearer {token}",
        }
        
        if token:
            headers["X-Auth-Token"] = token
        
        # Create a session to maintain cookies
        session_obj = requests.Session()
        
        # Forward all cookies from the original request
        for name, value in request.cookies.items():
            session_obj.cookies.set(name, value, path='/')
        
        if token:
            session_obj.cookies.set("auth_token", token, path='/')
        
        # Forward the request
        request_kwargs = {
            'headers': headers,
            'allow_redirects': False,
            'timeout': 120
        }
        
        if request.method == "GET":
            resp = session_obj.get(target_url, **request_kwargs)
        elif request.method == "POST":
            if request.is_json:
                request_kwargs['json'] = request.json
            else:
                request_kwargs['data'] = request.form
            resp = session_obj.post(target_url, **request_kwargs)
        else:
            resp = session_obj.request(request.method, target_url, **request_kwargs)
        
        # Return response
        from flask import Response
        response = Response(resp.content, status=resp.status_code)
        
        # Copy response headers
        for key, value in resp.headers.items():
            if key.lower() not in ['content-encoding', 'transfer-encoding', 'connection']:
                response.headers[key] = value
        
        # Copy cookies
        for cookie in session_obj.cookies:
            response.set_cookie(
                cookie.name,
                cookie.value,
                domain=None,
                path=cookie.path if cookie.path else '/',
                secure=False,
                httponly=True,
                samesite='Lax'
            )
        
        return response
    except Exception as e:
        logger.error(f"Error proxying tables-data request: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/api/dashboards", defaults={"path": ""}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
@app.route("/api/dashboards/", defaults={"path": ""}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
@app.route("/api/dashboards/<path:path>", methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
def dashboard_api_proxy(path):
    """Proxy dashboard API requests to monolithic app"""
    import requests
    
    # CRITICAL: Log at the start to verify request reaches gateway
    logger.info(f"=== DASHBOARD API PROXY CALLED ===")
    logger.info(f"path={path}, full_path={request.path}, method={request.method}")
    logger.info(f"Request URL: {request.url}")
    logger.info(f"Request headers: {dict(request.headers)}")
    logger.info(f"Request cookies: {list(request.cookies.keys())}")
    # Log cookie values (first 20 chars for security)
    if request.cookies:
        cookie_preview = {k: (v[:20] + '...' if len(v) > 20 else v) for k, v in request.cookies.items()}
        logger.info(f"Cookie values preview: {cookie_preview}")
    logger.info(f"Request remote_addr: {request.remote_addr}")
    logger.info(f"Request host: {request.host}")
    
    token = get_auth_token()
    if not token:
        logger.warning(f"Dashboard API proxy: No auth token found for path={path}, cookies={list(request.cookies.keys())}, headers={list(request.headers.keys())}")
        # Still proxy the request - let monolithic app handle authentication
        # This allows session-based auth to work
        logger.info(f"Proxying dashboard API request without token (session-based auth)")
    else:
        logger.info(f"Dashboard API proxy: Found auth token (length: {len(token)})")
    
    # Build target URL
    if path:
        target_url = f"{MONOLITHIC_APP_URL}/api/dashboards/{path}"
    else:
        target_url = f"{MONOLITHIC_APP_URL}/api/dashboards"
    
    # Add query string if present
    if request.query_string:
        target_url += f"?{request.query_string.decode()}"
    
    logger.info(f"Proxying dashboard API request to: {target_url}")
    
    try:
        # Forward request with cookies and headers
        headers = {}
        
        if token:
            headers["Authorization"] = f"Bearer {token}"
            headers["X-Auth-Token"] = token
        
        # Create a session to maintain cookies
        session_obj = requests.Session()
        
        # Forward all cookies from the original request
        for name, value in request.cookies.items():
            session_obj.cookies.set(name, value, path='/')
        
        if token:
            session_obj.cookies.set("auth_token", token, path='/')
        
        # Always forward cookie header for session sync in monolithic app
        cookie_header = request.headers.get('Cookie', '')
        if cookie_header:
            headers["Cookie"] = cookie_header
            if token and f"auth_token={token}" not in cookie_header:
                headers["Cookie"] = f"{cookie_header}; auth_token={token}"
        elif token:
            headers["Cookie"] = f"auth_token={token}"
        
        # Forward the request
        request_kwargs = {
            'headers': headers,
            'allow_redirects': False,
            'timeout': 120  # Increased timeout for dashboard API requests
        }
        
        if request.method == "GET":
            resp = session_obj.get(target_url, **request_kwargs)
        elif request.method == "POST":
            if request.is_json:
                request_kwargs['json'] = request.json
            else:
                request_kwargs['data'] = request.form
            resp = session_obj.post(target_url, **request_kwargs)
        else:
            resp = session_obj.request(request.method, target_url, **request_kwargs)
        
        logger.info(f"Monolithic app response: status={resp.status_code}, content_length={len(resp.content)}")
        
        # If we get 404, log more details
        if resp.status_code == 404:
            logger.error(f"⚠️ 404 from monolithic app for: {target_url}")
            logger.error(f"Request path: {request.path}, Method: {request.method}")
            logger.error(f"Response content (first 500 chars): {resp.text[:500]}")
            # Try to check if monolithic app is running
            try:
                health_check = session_obj.get(f"{MONOLITHIC_APP_URL}/health", timeout=5)
                logger.info(f"Monolithic app health check: {health_check.status_code}")
            except Exception as health_error:
                logger.error(f"⚠️ Cannot connect to monolithic app at {MONOLITHIC_APP_URL}: {health_error}")
                logger.error(f"Make sure monolithic app is running on port 5006")
        
        # Return response
        from flask import Response, jsonify
        response = Response(resp.content, status=resp.status_code)
        
        # Copy response headers
        for key, value in resp.headers.items():
            if key.lower() not in ['content-encoding', 'transfer-encoding', 'connection']:
                response.headers[key] = value
        
        # Copy cookies
        for cookie in session_obj.cookies:
            response.set_cookie(
                cookie.name,
                cookie.value,
                domain=None,
                path=cookie.path if cookie.path else '/',
                secure=False,
                httponly=True,
                samesite='Lax'
            )
        
        return response
    except requests.exceptions.ConnectionError as e:
        logger.error(f"✗ Connection error: Cannot connect to monolithic app at {MONOLITHIC_APP_URL}")
        logger.error(f"Make sure the monolithic app is running. Start it with: python start-monolithic-app.ps1")
        logger.error(f"Error details: {e}")
        return jsonify({
            "error": "Service unavailable",
            "message": "سرویس در دسترس نیست. لطفاً با مدیر سیستم تماس بگیرید.",
            "details": f"Cannot connect to {MONOLITHIC_APP_URL}"
        }), 503
    except Exception as e:
        logger.error(f"Error proxying dashboard API request: {e}", exc_info=True)
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({
            "error": str(e),
            "message": "خطا در ارتباط با سرور"
        }), 500

@app.route("/dashboard", defaults={"path": ""}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
@app.route("/dashboard/", defaults={"path": ""}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
@app.route("/dashboard/<path:path>", methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
@app.route("/dashboards", defaults={"path": ""}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
@app.route("/dashboards/", defaults={"path": ""}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
@app.route("/dashboards/<path:path>", methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
def dashboard_proxy(path):
    """Proxy dashboard requests to Dashboard Service or monolithic app"""
    import requests
    
    token = get_auth_token()
    if not token:
        redirect_uri = request.url_root.rstrip('/')
        return redirect(f"/auth/login?redirect_uri={redirect_uri}")
    
    # For now, proxy to monolithic app (Dashboard Service only has API endpoints, no HTML)
    # Monolithic app runs on port 5006 to avoid conflict with Gateway Service (port 5000)
    # MONOLITHIC_APP_URL is set at module level
    
    # Build target URL (monolithic app uses /dashboards prefix)
    # CRITICAL: Always use trailing slash for /dashboards to prevent redirect loops
    # Flask redirects /dashboards to /dashboards/, so we should always use /dashboards/
    if path:
        target_url = f"{MONOLITHIC_APP_URL}/dashboards/{path}"
    else:
        # Always add trailing slash to prevent redirect loops
        target_url = f"{MONOLITHIC_APP_URL}/dashboards/"
    
    # Add query string if present
    if request.query_string:
        target_url += f"?{request.query_string.decode()}"
    
    logger.info(f"Proxying dashboard request to: {target_url}")
    
    try:
        # Forward request with cookies and headers
        # Monolithic app uses Flask session, so we need to forward all cookies
        headers = {
            "Authorization": f"Bearer {token}",
        }
        
        # CRITICAL: Add auth_token to headers so monolithic app can sync session
        # This ensures auth_token is available even if cookies don't work
        if token:
            headers["X-Auth-Token"] = token
        
        # Create a session to maintain cookies
        session_obj = requests.Session()
        
        # Forward all cookies from the original request to maintain session
        for name, value in request.cookies.items():
            session_obj.cookies.set(name, value, path='/')
        
        # Also set auth_token cookie if we have it (for session sync in monolithic app)
        if token:
            session_obj.cookies.set("auth_token", token, path='/')
        
        # Forward the request (don't follow redirects automatically)
        # Handle different HTTP methods
        # CRITICAL: Increase timeout for dashboard requests, especially d8 (LMS monitoring)
        # which may take longer to process due to data fetching and visualization generation
        # Dashboard d8 processes large amounts of data and may need more time
        request_kwargs = {
            'headers': headers,
            'allow_redirects': False,
            'timeout': 120  # Increased from 30 to 120 seconds for dashboard requests
        }
        
        if request.method == "GET":
            resp = session_obj.get(target_url, **request_kwargs)
        elif request.method == "POST":
            # Handle both form data and JSON
            if request.is_json:
                request_kwargs['json'] = request.json
            else:
                request_kwargs['data'] = request.form
                if request.files:
                    request_kwargs['files'] = request.files
            resp = session_obj.post(target_url, **request_kwargs)
        elif request.method in ["PUT", "PATCH"]:
            # Handle both form data and JSON
            if request.is_json:
                request_kwargs['json'] = request.json
            else:
                request_kwargs['data'] = request.form
                if request.files:
                    request_kwargs['files'] = request.files
            resp = session_obj.request(request.method, target_url, **request_kwargs)
        elif request.method == "DELETE":
            resp = session_obj.delete(target_url, **request_kwargs)
        else:
            # For other methods (OPTIONS, HEAD, etc.)
            resp = session_obj.request(request.method, target_url, **request_kwargs)
        
        # Handle redirects - convert monolithic app URLs to gateway URLs
        if resp.status_code in [301, 302, 303, 307, 308]:
            location = resp.headers.get('Location') or ''
            logger.info(f"Dashboard redirect detected: {location}")
            
            # Ensure location is a string
            if location is None:
                location = ''
            
            # CRITICAL: Check if this is a redirect loop
            # If monolithic app redirects to /dashboards/ and we're already requesting /dashboards/,
            # this is a redirect loop - return the response directly instead of redirecting
            if location and ('/dashboards/' in location or location.endswith('/dashboards')):
                # Check if we're in a redirect loop
                if request.path in ['/dashboard', '/dashboard/', '/dashboards', '/dashboards/']:
                    # This is likely a redirect loop - try to get the actual response
                    # by following the redirect once more, but this time return the content directly
                    logger.warning(f"Potential redirect loop detected: {location}, request path: {request.path}")
                    # Build the target URL for the redirect
                    if location.startswith('http'):
                        redirect_url = location
                    elif location.startswith('/'):
                        redirect_url = f"{MONOLITHIC_APP_URL}{location}"
                    else:
                        redirect_url = f"{MONOLITHIC_APP_URL}/dashboards/{location}"
                    
                    # Try to get the final response by following redirects
                    try:
                        final_resp = session_obj.get(redirect_url, headers=headers, allow_redirects=True, timeout=30)
                        if final_resp.status_code == 200:
                            # Return the final response directly
                            from flask import Response
                            response = Response(final_resp.content, status=final_resp.status_code)
                            for key, value in final_resp.headers.items():
                                if key.lower() not in ['content-encoding', 'transfer-encoding', 'connection', 'location']:
                                    response.headers[key] = value
                            # Copy cookies
                            for cookie in session_obj.cookies:
                                response.set_cookie(
                                    cookie.name,
                                    cookie.value,
                                    domain=None,
                                    path=cookie.path if cookie.path else '/',
                                    secure=False,
                                    httponly=True,
                                    samesite='Lax'
                                )
                            logger.info(f"Returning final response directly to break redirect loop")
                            return response
                    except Exception as e:
                        logger.error(f"Error following redirect: {e}")
                        # Fall through to normal redirect handling
            
            # Parse the location URL
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(location)
            new_path = None
            
            # Handle both absolute URLs (with localhost:5006) and relative URLs
            if location and ('localhost:5006' in location or '127.0.0.1:5006' in location):
                # Absolute URL with localhost:5006 - extract path and query
                new_path = parsed.path or '/'
                if parsed.query:
                    new_path += f"?{parsed.query}"
            elif location and location.startswith('/'):
                # Relative URL - use as is
                new_path = location
            elif location:
                # Other absolute URL (e.g., https://...) - keep as is unless it's SSO
                if 'sso.cfu.ac.ir' in location:
                    # Keep SSO redirects as is
                    redirect_response = redirect(location)
                    for cookie in session_obj.cookies:
                        redirect_response.set_cookie(
                            cookie.name, cookie.value,
                            domain=None, path=cookie.path if cookie.path else '/',
                            secure=False, httponly=True, samesite='Lax'
                        )
                    return redirect_response
                else:
                    # Unknown absolute URL - use path only
                    new_path = parsed.path or '/'
                    if parsed.query:
                        new_path += f"?{parsed.query}"
            else:
                # Empty location - default to root
                new_path = '/'
            
            # Ensure new_path is set and is a string
            if new_path is None:
                new_path = '/'
            
            # CRITICAL: Handle /dashboards redirects correctly to prevent redirect loops
            # If monolithic app redirects to /dashboards/, keep it as /dashboards/ (not /dashboard/)
            # This prevents redirect loops when Flask redirects /dashboards to /dashboards/
            if new_path == '/dashboards' or new_path == '/dashboards/':
                # Keep as /dashboards/ to match the route
                new_path = '/dashboards/'
                logger.info(f"Keeping /dashboards/ redirect as is: {new_path}")
            elif new_path.startswith('/dashboards/'):
                # Keep /dashboards/ prefix for dashboard routes
                logger.info(f"Keeping /dashboards/ prefix: {new_path}")
            
            # Convert /login to /auth/login (gateway auth route)
            if new_path == '/login' or (new_path and new_path.startswith('/login?')):
                new_path = new_path.replace('/login', '/auth/login', 1)
                logger.info(f"Converted /login redirect to: {new_path}")
            
            # Return redirect through gateway
            redirect_response = redirect(new_path)
            
            # Copy cookies from monolithic app response
            for cookie in session_obj.cookies:
                redirect_response.set_cookie(
                    cookie.name,
                    cookie.value,
                    domain=None,
                    path=cookie.path if cookie.path else '/',
                    secure=False,  # Will be set by nginx if HTTPS
                    httponly=True,
                    samesite='Lax'
                )
            
            return redirect_response
        
        # Return response
        from flask import Response
        response = Response(resp.content, status=resp.status_code)
        
        # Copy response headers (except Location which we handle above)
        for key, value in resp.headers.items():
            if key.lower() not in ['content-encoding', 'transfer-encoding', 'connection', 'location']:
                response.headers[key] = value
        
        # Copy cookies from monolithic app response
        for cookie in session_obj.cookies:
            response.set_cookie(
                cookie.name,
                cookie.value,
                domain=None,
                path=cookie.path if cookie.path else '/',
                secure=False,
                httponly=True,
                samesite='Lax'
            )
        
        return response
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Error proxying dashboard request: Cannot connect to monolithic app at {MONOLITHIC_APP_URL}")
        logger.error(f"Make sure the monolithic app is running. Start it with: python start-monolithic-app.ps1")
        error_msg = f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>سرویس در دسترس نیست</title>
    <style>
        body {{ font-family: Tahoma, Arial, sans-serif; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 600px; margin: 50px auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #d32f2f; }}
        code {{ background: #f5f5f5; padding: 2px 6px; border-radius: 3px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>سرویس در دسترس نیست</h1>
        <p>سرویس داشبورد در حال حاضر در دسترس نیست. لطفاً با مدیر سیستم تماس بگیرید.</p>
        <p><small>جزئیات خطا: {str(e)}</small></p>
    </div>
</body>
</html>"""
        from flask import make_response
        response = make_response(error_msg, 503)
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        return response
    except Exception as e:
        logger.error(f"Error proxying dashboard request: {e}", exc_info=True)
        return f"Error connecting to dashboard service: {str(e)}", 500

@app.route("/auth/authorized")
def auth_authorized():
    """Handle SSO callback - proxy with proper session cookie handling"""
    import requests
    from flask import Response, make_response
    from urllib.parse import urlparse
    
    # Build target URL
    auth_url = f"{AUTH_SERVICE_URL}/authorized"
    if request.query_string:
        auth_url += f"?{request.query_string.decode()}"
    
    logger.info(f"Proxying /auth/authorized to Auth Service: {auth_url}")
    logger.info(f"Request cookies: {list(request.cookies.keys())}")
    
    # Create a session to maintain cookies between requests
    session_obj = requests.Session()
    
    # Copy ALL cookies from the incoming request to the session
    # This is critical - the session cookie from /auth/login must be preserved
    # Flask-Session uses a cookie named 'flask_session' by default (or 'session' in older versions)
    cookie_count = 0
    session_cookie_found = False
    
    for name, value in request.cookies.items():
        # Set cookie - requests library will handle domain/path automatically
        session_obj.cookies.set(name, value)
        cookie_count += 1
        
        # Check if this is a session cookie
        # Flask-Session uses 'flask_session' by default, but check for common session cookie names
        if name in ['flask_session', 'session', 'session_id', 'flask_session_id']:
            session_cookie_found = True
            logger.info(f"Found session cookie: {name} (length: {len(value)})")
        else:
            logger.info(f"Copied cookie: {name}")
    
    if cookie_count == 0:
        logger.warning("⚠️ No cookies found in request! Session will be lost.")
        logger.warning("This means the session cookie from /auth/login was not preserved.")
    else:
        logger.info(f"Total cookies copied: {cookie_count}")
        if not session_cookie_found:
            logger.warning("⚠️ Session cookie (flask_session, session, session_id, or flask_session_id) not found!")
            logger.warning("This will cause 'State mismatch' error in Auth Service.")
            logger.warning(f"Available cookies: {list(request.cookies.keys())}")
    
    try:
        # Prepare headers
        # CRITICAL: Set Host header to the public domain so Auth Service uses correct URLs
        headers = {
            'User-Agent': request.headers.get('User-Agent', ''),
            'Accept': request.headers.get('Accept', '*/*'),
            'Accept-Language': request.headers.get('Accept-Language', ''),
            'Host': 'bi.cfu.ac.ir',  # Use public domain, not localhost
            'X-Forwarded-Host': 'bi.cfu.ac.ir',  # Public domain
            'X-Forwarded-Proto': 'https',  # Use HTTPS
            'X-Forwarded-For': request.remote_addr,
            'X-Original-Host': request.host,  # Keep original for reference
        }
        
        # Make the request to Auth Service
        resp = session_obj.get(auth_url, headers=headers, allow_redirects=False, timeout=10)
        
        logger.info(f"Auth Service response: {resp.status_code}")
        logger.info(f"Response cookies from Auth Service: {list(session_obj.cookies.keys())}")
        
        # Handle redirects
        if resp.status_code in [301, 302, 303, 307, 308]:
            location = resp.headers.get('Location') or ''
            logger.info(f"Original redirect location: {location}")
            
            # Ensure location is a string
            if location is None:
                location = ''
            
            # Convert internal Docker URLs (auth-service:5001) to /auth/ paths
            if location and ('auth-service:5001' in location or 'auth-service' in location):
                # Extract path from internal URL
                from urllib.parse import urlparse
                parsed = urlparse(location)
                location = parsed.path
                if parsed.query:
                    location += f"?{parsed.query}"
                logger.info(f"Converted from internal URL to: {location}")
            
            # If redirect is to Auth Service URL, convert to /auth/ path
            if location and AUTH_SERVICE_URL and AUTH_SERVICE_URL in location:
                location = location.replace(AUTH_SERVICE_URL, '').lstrip('/')
                if not location.startswith('/auth/'):
                    location = f"/auth/{location}"
                logger.info(f"Converted AUTH_SERVICE_URL to: {location}")
            
            # If it's an absolute URL to sso.cfu.ac.ir, keep it as is (this is the redirect to SSO)
            elif location and 'sso.cfu.ac.ir' in location:
                # This is the redirect to SSO - keep it as is
                logger.info(f"Keeping absolute URL to sso.cfu.ac.ir: {location}")
                # Don't modify it - it's the correct redirect to SSO
            # If it's an absolute URL to bi.cfu.ac.ir, keep it as is (this is the final redirect after login)
            elif location and 'bi.cfu.ac.ir' in location:
                # This is the final redirect after successful login - keep it as is
                logger.info(f"Keeping absolute URL to bi.cfu.ac.ir: {location}")
                # Don't modify it - it's the correct redirect
            # If it's a relative path starting with /, ensure it goes through /auth/
            elif location and location.startswith('/') and not location.startswith('/auth/'):
                # Check if it's an Auth Service route (login, authorized, etc.)
                if location in ['/login', '/authorized', '/logout'] or location.startswith('/api/auth/'):
                    location = f"/auth{location}"
                    logger.info(f"Converted relative path to: {location}")
            
            # If it's an absolute URL to localhost:5001, convert it
            elif location and ('localhost:5001' in location or '127.0.0.1:5001' in location):
                from urllib.parse import urlparse
                parsed = urlparse(location)
                location = parsed.path
                if parsed.query:
                    location += f"?{parsed.query}"
                if not location.startswith('/auth/'):
                    location = f"/auth{location}"
                logger.info(f"Converted localhost URL to: {location}")
            
            logger.info(f"Final redirect location: {location}")
            response = redirect(location)
            
            # CRITICAL: Copy ALL cookies from Auth Service response to client
            # This includes the session cookie and auth_token cookie
            for cookie in session_obj.cookies:
                cookie_domain = cookie.domain if cookie.domain else None
                cookie_path = cookie.path if cookie.path else '/'
                cookie_secure = cookie.secure if hasattr(cookie, 'secure') else True
                
                # Adjust cookie settings for Gateway
                # If we're on localhost or using HTTP, make cookie non-secure
                if request.host.startswith('localhost') or request.host.startswith('127.0.0.1') or request.scheme == 'http':
                    cookie_secure = False  # Allow HTTP cookies for localhost
                
                response.set_cookie(
                    cookie.name,
                    cookie.value,
                    domain=cookie_domain,
                    path=cookie_path,
                    secure=cookie_secure,
                    httponly=True,
                    samesite='Lax',
                    max_age=cookie.expires if hasattr(cookie, 'expires') and cookie.expires else None
                )
                logger.info(f"Set cookie in response: {cookie.name} (domain={cookie_domain}, path={cookie_path}, secure={cookie_secure})")
            
            return response
        
        # Return response with cookies (for non-redirect responses)
        response = make_response(resp.content, resp.status_code)
        
        # Copy ALL cookies from Auth Service response
        for cookie in session_obj.cookies:
            cookie_domain = cookie.domain if cookie.domain else None
            cookie_path = cookie.path if cookie.path else '/'
            cookie_secure = cookie.secure if hasattr(cookie, 'secure') else True
            
            # Adjust cookie settings for Gateway
            # If we're on localhost or using HTTP, make cookie non-secure
            if request.host.startswith('localhost') or request.host.startswith('127.0.0.1') or request.scheme == 'http':
                cookie_secure = False  # Allow HTTP cookies for localhost
            
            response.set_cookie(
                cookie.name,
                cookie.value,
                domain=cookie_domain,
                path=cookie_path,
                secure=cookie_secure,
                httponly=True,
                samesite='Lax',
                max_age=cookie.expires if hasattr(cookie, 'expires') and cookie.expires else None
            )
            logger.info(f"Set cookie in response: {cookie.name} (domain={cookie_domain}, path={cookie_path}, secure={cookie_secure})")
        
        # Copy response headers (except cookies which we handle separately)
        for key, value in resp.headers.items():
            if key.lower() not in ['content-encoding', 'transfer-encoding', 'connection', 'set-cookie']:
                response.headers[key] = value
        
        return response
        
    except Exception as e:
        logger.error(f"Error proxying /auth/authorized: {e}", exc_info=True)
        import traceback
        logger.error(traceback.format_exc())
        # Fallback: redirect to Auth Service directly (will only work if Nginx is routing)
        return redirect(auth_url)

@app.route("/auth/<path:path>")
def auth_proxy(path):
    """Proxy auth requests to Auth Service (except /authorized which needs direct redirect)"""
    import requests
    from urllib.parse import urlencode
    
    # Build target URL
    auth_url = f"{AUTH_SERVICE_URL}/{path}"
    if request.query_string:
        auth_url += f"?{request.query_string.decode()}"
    
    logger.info(f"Proxying request to Auth Service: {auth_url}")
    
    # Forward the request to Auth Service
    try:
        # Prepare headers
        # CRITICAL: Set Host header to the public domain so Auth Service uses correct URLs
        headers = dict(request.headers)
        headers.pop('Host', None)
        headers['Host'] = 'bi.cfu.ac.ir'  # Use public domain, not localhost
        headers['X-Forwarded-Host'] = 'bi.cfu.ac.ir'  # Public domain
        headers['X-Forwarded-Proto'] = 'https'  # Use HTTPS
        headers['X-Original-Host'] = request.host  # Keep original for reference
        
        # Use Session to preserve cookies between requests
        session_obj = requests.Session()
        # Copy cookies from request to session
        for name, value in request.cookies.items():
            session_obj.cookies.set(name, value)
        
        if request.method == "GET":
            resp = session_obj.get(auth_url, headers=headers, allow_redirects=False, timeout=10)
        elif request.method == "POST":
            resp = session_obj.post(auth_url, data=request.form, headers=headers, allow_redirects=False, timeout=10)
        else:
            return redirect(auth_url)
        
        # Handle redirects - convert internal URLs to /auth/ URLs
        if resp.status_code in [301, 302, 303, 307, 308]:
            location = resp.headers.get('Location') or ''
            logger.info(f"Original redirect location: {location}")
            
            # Ensure location is a string
            if location is None:
                location = ''
            
            # Convert internal Docker URLs (auth-service:5001) to /auth/ paths
            if location and ('auth-service:5001' in location or 'auth-service' in location):
                # Extract path from internal URL
                from urllib.parse import urlparse
                parsed = urlparse(location)
                location = parsed.path or '/'
                if parsed.query:
                    location += f"?{parsed.query}"
                logger.info(f"Converted from internal URL to: {location}")
            
            # If redirect is to Auth Service URL, convert to /auth/ path
            if location and AUTH_SERVICE_URL and AUTH_SERVICE_URL in location:
                location = location.replace(AUTH_SERVICE_URL, '').lstrip('/')
                if not location.startswith('/auth/'):
                    location = f"/auth/{location}"
                logger.info(f"Converted AUTH_SERVICE_URL to: {location}")
            
            # If it's a relative path starting with /, ensure it goes through /auth/
            elif location and location.startswith('/') and not location.startswith('/auth/'):
                # Check if it's an Auth Service route (login, authorized, etc.)
                if location in ['/login', '/authorized', '/logout'] or location.startswith('/api/auth/'):
                    location = f"/auth{location}"
                    logger.info(f"Converted relative path to: {location}")
            
            # If it's an absolute URL to localhost:5001, convert it
            elif 'localhost:5001' in location or '127.0.0.1:5001' in location:
                from urllib.parse import urlparse
                parsed = urlparse(location)
                location = parsed.path
                if parsed.query:
                    location += f"?{parsed.query}"
                if not location.startswith('/auth/'):
                    location = f"/auth{location}"
                logger.info(f"Converted localhost URL to: {location}")
            
            logger.info(f"Final redirect location: {location}")
            
            # CRITICAL: Copy cookies from Auth Service response before redirecting
            # This is needed for /auth/login to preserve session
            redirect_response = redirect(location)
            
            # Copy cookies from session_obj to redirect response
            # Track which cookies we've already set to avoid duplicates
            cookies_set = set()
            
            # CRITICAL: First check Set-Cookie headers from response
            # Flask-Session sets cookies via Set-Cookie headers, which may not be in session_obj.cookies
            # Always check Set-Cookie headers FIRST, even if session_obj.cookies exists
            # Use get() instead of get_list() for compatibility
            set_cookie_header = resp.headers.get('Set-Cookie')
            set_cookie_headers = []
            if set_cookie_header:
                # If there's only one Set-Cookie header, make it a list
                if isinstance(set_cookie_header, str):
                    set_cookie_headers = [set_cookie_header]
                elif isinstance(set_cookie_header, list):
                    set_cookie_headers = set_cookie_header
                else:
                    # Try get_list if available
                    try:
                        set_cookie_headers = resp.headers.get_list('Set-Cookie')
                    except:
                        set_cookie_headers = [set_cookie_header] if set_cookie_header else []
            if set_cookie_headers:
                logger.info(f"Found {len(set_cookie_headers)} Set-Cookie headers in redirect response")
                for set_cookie_header in set_cookie_headers:
                        # Parse Set-Cookie header
                        parts = set_cookie_header.split(';')
                        cookie_name_value = parts[0].strip()
                        if '=' in cookie_name_value:
                            cookie_name, cookie_value = cookie_name_value.split('=', 1)
                            cookie_name = cookie_name.strip()
                            cookie_value = cookie_value.strip()
                            
                            # Skip if we already set this cookie from session_obj.cookies
                            if cookie_name in cookies_set:
                                logger.debug(f"Skipping duplicate cookie: {cookie_name}")
                                continue
                            
                            # Parse cookie attributes
                            cookie_domain = None
                            cookie_path = '/'
                            cookie_secure = False
                            cookie_max_age = None
                            
                            for part in parts[1:]:
                                part = part.strip()
                                if part.lower().startswith('domain='):
                                    cookie_domain = part.split('=', 1)[1].strip()
                                elif part.lower().startswith('path='):
                                    cookie_path = part.split('=', 1)[1].strip()
                                elif part.lower() == 'secure':
                                    cookie_secure = True
                                elif part.lower().startswith('max-age='):
                                    try:
                                        cookie_max_age = int(part.split('=', 1)[1].strip())
                                    except:
                                        pass
                            
                            # Adjust cookie settings for Gateway
                            # If we're on localhost or using HTTP, make cookie non-secure
                            if request.host.startswith('localhost') or request.host.startswith('127.0.0.1') or request.scheme == 'http':
                                cookie_secure = False  # Allow HTTP cookies for localhost
                            # For HTTPS on bi.cfu.ac.ir, keep secure=True
                            # CRITICAL: For redirects to SSO, we need to set cookies with domain=None or domain='bi.cfu.ac.ir'
                            # so they're available when the browser comes back from SSO
                            if 'sso.cfu.ac.ir' in location:
                                # For SSO redirects, set domain to None (current domain) or 'bi.cfu.ac.ir'
                                # This ensures cookies are available when browser returns from SSO
                                cookie_domain = None  # Use current domain (bi.cfu.ac.ir)
                            
                            redirect_response.set_cookie(
                                cookie_name,
                                cookie_value,
                                domain=cookie_domain,
                                path=cookie_path,
                                secure=cookie_secure,
                                httponly=True,
                                samesite='Lax',
                                max_age=cookie_max_age
                            )
                            logger.info(f"Set cookie in redirect response (from Set-Cookie header): {cookie_name} (domain={cookie_domain}, path={cookie_path}, secure={cookie_secure})")
                            cookies_set.add(cookie_name)
            
            if len(cookies_set) == 0:
                logger.warning("⚠️ No cookies found in session_obj or Set-Cookie headers from Auth Service redirect response")
                logger.warning("This will cause 'State mismatch' error in Auth Service.")
            else:
                logger.info(f"✅ Successfully set {len(cookies_set)} cookies in redirect response: {list(cookies_set)}")
            
            return redirect_response
        
        # Return response with cookies
        from flask import Response
        # Filter out headers that shouldn't be forwarded
        response_headers = {}
        for key, value in resp.headers.items():
            if key.lower() not in ['content-encoding', 'transfer-encoding', 'connection', 'set-cookie']:
                response_headers[key] = value
        
        response = Response(resp.content, status=resp.status_code, headers=response_headers)
        
        # CRITICAL: Copy ALL cookies from Auth Service response to client
        # This is needed for /auth/login to preserve session
        # Use session_obj.cookies which contains all cookies from the response
        # Track which cookies we've set to avoid duplicates
        cookies_set = set()
        
        if session_obj.cookies:
            logger.info(f"Found {len(session_obj.cookies)} cookies in session from Auth Service")
            for cookie in session_obj.cookies:
                cookies_set.add(cookie.name)
                cookie_domain = cookie.domain if cookie.domain else None
                cookie_path = cookie.path if cookie.path else '/'
                cookie_secure = cookie.secure if hasattr(cookie, 'secure') else False
                
                # Adjust cookie settings for Gateway
                # If we're on localhost, make cookie non-secure for HTTP
                if request.host.startswith('localhost') or request.host.startswith('127.0.0.1'):
                    cookie_secure = False  # Allow HTTP cookies for localhost
                
                # Set cookie in response
                response.set_cookie(
                    cookie.name,
                    cookie.value,
                    domain=cookie_domain,
                    path=cookie_path,
                    secure=cookie_secure,
                    httponly=True,
                    samesite='Lax',
                    max_age=cookie.expires if hasattr(cookie, 'expires') and cookie.expires else None
                )
                logger.info(f"Set cookie in response: {cookie.name} (domain={cookie_domain}, path={cookie_path}, secure={cookie_secure})")
        
        # CRITICAL: Also check Set-Cookie headers from response
        # Flask-Session sets cookies via Set-Cookie headers, which may not be in session_obj.cookies
        # Always check Set-Cookie headers even if session_obj.cookies exists
        # Use get() instead of get_list() for compatibility
        set_cookie_header = resp.headers.get('Set-Cookie')
        set_cookie_headers = []
        if set_cookie_header:
            # If there's only one Set-Cookie header, make it a list
            if isinstance(set_cookie_header, str):
                set_cookie_headers = [set_cookie_header]
            elif isinstance(set_cookie_header, list):
                set_cookie_headers = set_cookie_header
            else:
                # Try get_list if available
                try:
                    set_cookie_headers = resp.headers.get_list('Set-Cookie')
                except:
                    set_cookie_headers = [set_cookie_header] if set_cookie_header else []
        if set_cookie_headers:
            logger.info(f"Found {len(set_cookie_headers)} Set-Cookie headers from Auth Service")
            for set_cookie_header in set_cookie_headers:
                # Parse Set-Cookie header: name=value; Path=/; Domain=...; Secure; HttpOnly
                parts = set_cookie_header.split(';')
                cookie_name_value = parts[0].strip()
                if '=' in cookie_name_value:
                    cookie_name, cookie_value = cookie_name_value.split('=', 1)
                    cookie_name = cookie_name.strip()
                    cookie_value = cookie_value.strip()
                    
                    # Skip if we already set this cookie from session_obj.cookies
                    if cookie_name in cookies_set:
                        logger.debug(f"Skipping duplicate cookie: {cookie_name}")
                        continue
                    
                    # Parse cookie attributes
                    cookie_domain = None
                    cookie_path = '/'
                    cookie_secure = False
                    cookie_httponly = False
                    cookie_samesite = 'Lax'
                    cookie_max_age = None
                    
                    for part in parts[1:]:
                        part = part.strip()
                        if part.lower().startswith('domain='):
                            cookie_domain = part.split('=', 1)[1].strip()
                        elif part.lower().startswith('path='):
                            cookie_path = part.split('=', 1)[1].strip()
                        elif part.lower() == 'secure':
                            cookie_secure = True
                        elif part.lower() == 'httponly':
                            cookie_httponly = True
                        elif part.lower().startswith('samesite='):
                            cookie_samesite = part.split('=', 1)[1].strip()
                        elif part.lower().startswith('max-age='):
                            try:
                                cookie_max_age = int(part.split('=', 1)[1].strip())
                            except:
                                pass
                    
                    # Adjust cookie settings for Gateway
                    # If we're on localhost, make cookie non-secure for HTTP
                    if request.host.startswith('localhost') or request.host.startswith('127.0.0.1'):
                        cookie_secure = False  # Allow HTTP cookies for localhost
                    
                    # Set cookie in response
                    response.set_cookie(
                        cookie_name,
                        cookie_value,
                        domain=cookie_domain,
                        path=cookie_path,
                        secure=cookie_secure,
                        httponly=cookie_httponly,
                        samesite=cookie_samesite,
                        max_age=cookie_max_age
                    )
                    logger.info(f"Set cookie in response (from Set-Cookie header): {cookie_name} (domain={cookie_domain}, path={cookie_path}, secure={cookie_secure})")
                    cookies_set.add(cookie_name)
        
        if len(cookies_set) == 0:
            logger.warning("No cookies found in session_obj or Set-Cookie headers from Auth Service response")
        
        return response
    except Exception as e:
        logger.error(f"Error proxying auth request to {auth_url}: {e}", exc_info=True)
        # Fallback: redirect to Auth Service directly
        return redirect(auth_url)

@app.route("/health")
def health():
    """Health check endpoint"""
    from flask import jsonify
    import requests
    
    # Check if monolithic app is running
    monolithic_status = "unknown"
    try:
        health_resp = requests.get(f"{MONOLITHIC_APP_URL}/health", timeout=2)
        monolithic_status = "running" if health_resp.status_code == 200 else f"error_{health_resp.status_code}"
    except requests.exceptions.ConnectionError:
        monolithic_status = "not_running"
    except Exception as e:
        monolithic_status = f"error_{str(e)}"
    
    return jsonify({
        "status": "healthy",
        "service": "gateway-service",
        "monolithic_app": {
            "url": MONOLITHIC_APP_URL,
            "status": monolithic_status
        }
    }), 200

if __name__ == "__main__":
    import sys
    try:
        # Check if port is already in use
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', 5000))
        sock.close()
        if result == 0:
            logger.error("Port 5000 is already in use. Please stop the existing service first.")
            logger.error("To find and kill the process using port 5000, run:")
            logger.error("  netstat -ano | findstr :5000")
            logger.error("  taskkill /F /PID <PID>")
            sys.exit(1)
        
        logger.info("Starting Gateway Service on port 5000...")
        # Use use_reloader=False to prevent issues with multiple processes
        # In production, use a proper WSGI server like waitress or gunicorn
        app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
    except OSError as e:
        if e.errno == 98 or "Address already in use" in str(e):
            logger.error(f"Port 5000 is already in use: {e}")
            logger.error("Please stop the existing service first.")
            sys.exit(1)
        else:
            logger.error(f"Error starting Gateway Service: {e}", exc_info=True)
            raise
    except Exception as e:
        logger.error(f"Unexpected error starting Gateway Service: {e}", exc_info=True)
        raise

