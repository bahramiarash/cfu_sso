"""
Survey System Blueprint
Blueprint for survey managers and public survey interface
"""
from flask import Blueprint

survey_bp = Blueprint('survey', __name__, url_prefix='/survey')

from . import manager_routes, public_routes, utils

