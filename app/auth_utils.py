# auth_utils.py

import logging
from flask import session, redirect, request, url_for
from functools import wraps

logging.basicConfig(level=logging.INFO)

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "sso_token" not in session:
            logging.info("User not authenticated, redirecting to login")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated

