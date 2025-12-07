"""
Admin Panel Utilities
Helper functions for admin panel
"""
from functools import wraps
from flask import abort, request, session
from flask_login import current_user
from models import User
from admin_models import AccessLog
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def admin_required(f):
    """Decorator to require admin access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not current_user.is_admin():
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def log_action(action: str, resource_type: str = None, resource_id: str = None, details: dict = None, user_id: int = None):
    """
    Log user action to AccessLog
    
    Args:
        action: Action performed (e.g., 'view_dashboard', 'modify_user')
        resource_type: Type of resource (e.g., 'dashboard', 'user')
        resource_id: ID of resource
        details: Additional context as dictionary
        user_id: Optional user ID (if None, uses current_user)
    """
    try:
        from extensions import db
        
        # Determine user_id
        if user_id is None:
            if current_user is None or not current_user.is_authenticated:
                return
            user_id = current_user.id
        
        log_entry = AccessLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            ip_address=request.remote_addr if hasattr(request, 'remote_addr') else None,
            user_agent=request.headers.get('User-Agent') if hasattr(request, 'headers') else None,
            request_path=request.path if hasattr(request, 'path') else None,
            request_method=request.method if hasattr(request, 'method') else None,
            details=details or {}
        )
        
        db.session.add(log_entry)
        db.session.commit()
        
    except Exception as e:
        logger.error(f"Error logging action: {e}", exc_info=True)


def get_user_org_context(user: User) -> dict:
    """Get user's organizational context"""
    return {
        'province_code': user.province_code,
        'university_code': user.university_code,
        'faculty_code': user.faculty_code,
        'access_levels': [acc.level for acc in user.access_levels]
    }

