"""
Utility functions for Knowledge Management Service
"""
import os
import sys
import logging
from functools import wraps
from flask import request, jsonify

# Import from shared utils - use direct file import to avoid naming conflict
# Since this file is named utils.py, we can't use "from utils import" 
# Instead, import directly from the file
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
shared_utils_file = os.path.join(parent_dir, 'shared', 'utils', 'auth_client.py')

if os.path.exists(shared_utils_file):
    import importlib.util
    spec = importlib.util.spec_from_file_location("shared_auth_client", shared_utils_file)
    shared_auth_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shared_auth_module)
    AuthClient = shared_auth_module.AuthClient
else:
    # Fallback: try adding to path and importing
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    # Import with a different approach to avoid conflict
    import importlib
    shared_utils = importlib.import_module('shared.utils.auth_client')
    AuthClient = shared_utils.AuthClient

logger = logging.getLogger(__name__)

# Get AUTH_SERVICE_URL from environment
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:5001")

# Lazy initialization of auth_client to avoid blocking on startup
_auth_client = None

def get_auth_client():
    """Get or create AuthClient instance (lazy initialization)"""
    global _auth_client
    if _auth_client is None:
        _auth_client = AuthClient(AUTH_SERVICE_URL)
    return _auth_client


def get_auth_token():
    """Extract JWT token from request"""
    auth_header = request.headers.get("Authorization") or ""
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.replace("Bearer ", "")
    return request.cookies.get("auth_token")


def login_required(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = get_auth_token()
        if not token:
            return jsonify({"error": "Authentication required", "message": "لطفاً وارد سیستم شوید"}), 401
        
        # Validate token
        auth_client = get_auth_client()
        result = auth_client.validate_token(token)
        if "error" in result:
            return jsonify({"error": "Invalid token", "message": "توکن نامعتبر است"}), 401
        
        # Add user info to kwargs
        kwargs['user'] = result.get("user", {})
        return f(*args, **kwargs)
    
    return decorated_function


def get_user_id():
    """Get current user ID from token"""
    token = get_auth_token()
    if not token:
        return None
    
    auth_client = get_auth_client()
    result = auth_client.validate_token(token)
    if "error" in result:
        return None
    
    user = result.get("user", {})
    return user.get("id")

