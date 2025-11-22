# app/decorators.py

from flask import abort
from flask_login import current_user
from functools import wraps

def admin_or_pm_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['admin', 'project_manager']:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function
