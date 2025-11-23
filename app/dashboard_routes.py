"""
Dashboard Routes
Auto-registers all dashboards and provides route handlers
"""
from flask import Blueprint, render_template, request, session
from flask_login import current_user
from auth_utils import requires_auth
from dashboards.registry import DashboardRegistry
from dashboards.context import get_user_context, UserContext
from dashboards.dashboards import *  # Import all dashboards to register them
import logging

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboards")


@dashboard_bp.route("/")
@requires_auth
def dashboard_list():
    """List all accessible dashboards for current user"""
    try:
        user_context = get_user_context()
        dashboards = DashboardRegistry.get_accessible_dashboards(user_context)
        
        user_info = session.get('user_info', {})
        
        response = render_template(
            "dashboard_list.html",
            dashboards=dashboards,
            user=user_info,
            user_context=user_context.to_dict()
        )
        return response
    except Exception as e:
        logger.error(f"Error listing dashboards: {e}", exc_info=True)
        return render_template("error.html", error="خطا در نمایش لیست داشبوردها"), 500


@dashboard_bp.route("/<dashboard_id>")
@requires_auth
def show_dashboard(dashboard_id):
    """Show specific dashboard with context-aware data filtering"""
    try:
        # Get dashboard from registry
        dashboard = DashboardRegistry.get(dashboard_id)
        if not dashboard:
            return render_template("error.html", error="داشبورد یافت نشد"), 404
        
        # Get user context
        user_context = get_user_context()
        
        # Check access
        if not dashboard.check_access(user_context):
            return render_template("error.html", error="شما دسترسی به این داشبورد را ندارید"), 403
        
        # Get filters from request parameters
        filters = {}
        if request.args.get('province_code'):
            filters['province_code'] = int(request.args.get('province_code'))
        if request.args.get('university_code'):
            filters['university_code'] = int(request.args.get('university_code'))
        if request.args.get('faculty_code'):
            filters['faculty_code'] = int(request.args.get('faculty_code'))
        if request.args.get('date_from'):
            filters['date_from'] = request.args.get('date_from')
        if request.args.get('date_to'):
            filters['date_to'] = request.args.get('date_to')
        
        # Handle dashboard request
        return dashboard.handle_request(user_context=user_context, filters=filters, **request.args)
        
    except ValueError as e:
        # Authentication/authorization error
        logger.warning(f"Access denied for dashboard {dashboard_id}: {e}")
        return render_template("error.html", error="شما دسترسی به این داشبورد را ندارید"), 403
    except Exception as e:
        logger.error(f"Error showing dashboard {dashboard_id}: {e}", exc_info=True)
        return render_template("error.html", error=f"خطا در نمایش داشبورد: {str(e)}"), 500


# Register individual dashboard routes for backward compatibility
# These routes will use the new architecture but maintain old URLs
@dashboard_bp.route("/d1")
@requires_auth
def dashboard_d1():
    """Legacy route for d1 - redirects to new architecture"""
    return show_dashboard("d1")

@dashboard_bp.route("/d2")
@requires_auth
def dashboard_d2():
    """Legacy route for d2 - redirects to new architecture"""
    return show_dashboard("d2")

@dashboard_bp.route("/d3")
@requires_auth
def dashboard_d3():
    """Legacy route for d3 - redirects to new architecture"""
    return show_dashboard("d3")

@dashboard_bp.route("/d7")
@requires_auth
def dashboard_d7():
    """Legacy route for d7 - redirects to new architecture"""
    return show_dashboard("d7")

@dashboard_bp.route("/d8")
@requires_auth
def dashboard_d8():
    """Legacy route for d8 - redirects to new architecture"""
    return show_dashboard("d8")

@dashboard_bp.route("/students")
@requires_auth
def dashboard_students():
    """Legacy route for students dashboard - redirects to new architecture"""
    return show_dashboard("students")

