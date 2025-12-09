"""
Admin Panel Blueprint
Professional admin panel for dashboard management
"""
from flask import Blueprint
import os

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

from . import routes, utils, sync_handlers, survey_routes
