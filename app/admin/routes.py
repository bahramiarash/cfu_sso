"""
Admin Panel Routes
Routes for admin panel functionality
"""
from flask import render_template, request, jsonify, redirect, url_for, flash, session, Response
from flask_login import login_required, current_user
from . import admin_bp
from .utils import admin_required, log_action, get_user_org_context
from models import User, AccessLevel as AccessLevelModel
from admin_models import DashboardAccess, AccessLog, DataSync, DashboardConfig, ChartConfig, TemplateVersion
from extensions import db
from sqlalchemy import or_, func
from dashboards.registry import DashboardRegistry
from datetime import datetime, timedelta
from jdatetime import datetime as jdatetime
import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# Helper function to apply chart configurations to HTML template
def apply_chart_configs_to_html(template_path: Path, chart_configs: list) -> bool:
    """
    Apply chart configurations to HTML template file.
    Updates chart types, titles, and other settings in the JavaScript code.
    
    Args:
        template_path: Path to the HTML template file
        chart_configs: List of chart configuration dictionaries
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Read template content
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        import re
        
        # Apply configurations to each chart
        for chart_config in chart_configs:
            chart_id = chart_config.get('chart_id')
            if not chart_id:
                continue
            
            chart_type = chart_config.get('chart_type')
            title = chart_config.get('title')
            show_legend = chart_config.get('show_legend')
            show_labels = chart_config.get('show_labels')
            
            # 1. Update chart type in JavaScript
            # Find getElementById for this chart_id, then find the Chart initialization after it
            ctx_pattern = rf'getElementById\s*\([\'"]{re.escape(chart_id)}[\'"]\)'
            ctx_match = re.search(ctx_pattern, content)
            
            if ctx_match and chart_type:
                # Find the Chart initialization after this context
                start_pos = ctx_match.end()
                # Look for "new Chart" within next 2000 characters
                chart_block = content[start_pos:start_pos + 2000]
                chart_init_match = re.search(r'new\s+Chart\s*\([^,]+,\s*\{', chart_block)
                
                if chart_init_match:
                    # Find the type: 'xxx' pattern within this Chart initialization
                    chart_start_in_block = chart_init_match.end()
                    chart_init_full = chart_block[chart_start_in_block:]
                    
                    # Find type: 'xxx' pattern
                    type_pattern = r"type\s*:\s*['\"]([^'\"]+)['\"]"
                    type_match = re.search(type_pattern, chart_init_full)
                    
                    if type_match:
                        old_type = type_match.group(1)
                        if old_type != chart_type:
                            # Replace the type
                            absolute_pos = start_pos + chart_start_in_block + type_match.start()
                            type_full_match = type_match.group(0)
                            new_type = type_full_match.replace(old_type, chart_type)
                            content = content[:absolute_pos] + new_type + content[absolute_pos + len(type_full_match):]
                            logger.debug(f"Updated chart type for {chart_id} from {old_type} to {chart_type}")
            
            # 2. Update chart title in h4/h5 tags before canvas
            if title:
                # Find h4/h5 tag that appears before the canvas with this chart_id
                # Pattern: <h4/h5>...</h4/h5> followed by canvas with id="chart_id"
                title_section_pattern = rf'(<h[45][^>]*class=["\'][^"\']*mb-3[^"\']*["\'][^>]*>)([^<]+)(</h[45]>)(\s*<canvas[^>]*id=["\']{re.escape(chart_id)}["\'])'
                title_match = re.search(title_section_pattern, content, re.DOTALL | re.IGNORECASE)
                
                if title_match:
                    current_title = title_match.group(2).strip()
                    if current_title != title:
                        # Replace the title text
                        title_start = title_match.start(2)
                        title_end = title_match.end(2)
                        content = content[:title_start] + title + content[title_end:]
                        logger.debug(f"Updated title for {chart_id} from '{current_title}' to '{title}'")
            
            # 3. Update legend display in plugins section
            if show_legend is not None:
                # Find the Chart initialization for this chart and update legend.display
                # This is more complex - find the options.plugins.legend.display
                # We'll search for legend configuration near the chart_id context
                if ctx_match:
                    start_pos = ctx_match.end()
                    chart_block = content[start_pos:start_pos + 3000]
                    
                    # Find legend display setting
                    legend_display_pattern = r'legend\s*:\s*\{[^}]*display\s*:\s*(true|false)'
                    legend_match = re.search(legend_display_pattern, chart_block, re.DOTALL)
                    
                    if legend_match:
                        old_value = legend_match.group(1)
                        new_value = 'true' if show_legend else 'false'
                        if old_value != new_value:
                            absolute_pos = start_pos + legend_match.start(1)
                            content = content[:absolute_pos] + new_value + content[absolute_pos + len(old_value):]
                            logger.debug(f"Updated legend display for {chart_id} to {new_value}")
            
            # 4. Update show_labels (datalabels display)
            if show_labels is not None:
                if ctx_match:
                    start_pos = ctx_match.end()
                    chart_block = content[start_pos:start_pos + 3000]
                    
                    # Find datalabels display setting
                    datalabels_pattern = r'datalabels\s*:\s*\{[^}]*display\s*:\s*(true|false)'
                    datalabels_match = re.search(datalabels_pattern, chart_block, re.DOTALL)
                    
                    if datalabels_match:
                        old_value = datalabels_match.group(1)
                        new_value = 'true' if show_labels else 'false'
                        if old_value != new_value:
                            absolute_pos = start_pos + datalabels_match.start(1)
                            content = content[:absolute_pos] + new_value + content[absolute_pos + len(old_value):]
                            logger.debug(f"Updated datalabels display for {chart_id} to {new_value}")
        
        # Only write if content changed
        if content != original_content:
            # Write updated content back to file
            with open(template_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"Successfully applied chart configurations to {template_path.name}")
            return True
        else:
            logger.info(f"No changes needed for {template_path.name}")
            return True
        
    except Exception as e:
        logger.error(f"Error applying chart configs to HTML: {e}", exc_info=True)
        return False

# Error handler for admin blueprint - handles errors before app-level handler
@admin_bp.errorhandler(500)
def admin_500_error(e):
    """Handle 500 errors in admin routes - return HTML, not JSON"""
    import traceback
    error_traceback = traceback.format_exc()
    logger.error(f"Admin 500 Error in {request.path}: {e}")
    logger.error(f"Traceback: {error_traceback}")
    
    # For template edit pages, return HTML error page
    if request.path.startswith('/admin/dashboards/templates/'):
        path_parts = request.path.split('/')
        if len(path_parts) >= 5:
            template_name = path_parts[4]
            if template_name.endswith('.html') and request.method == 'GET':
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
    
    # For other admin routes, return HTML error page
    error_html = f"""<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
    <meta charset="utf-8">
    <title>خطای سرور</title>
    <style>
        body {{ font-family: Tahoma, Arial; padding: 20px; background: #f5f5f5; }}
        .error-box {{ background: white; padding: 20px; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        h1 {{ color: #d32f2f; }}
        pre {{ background: #f5f5f5; padding: 10px; border-radius: 3px; overflow-x: auto; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="error-box">
        <h1>خطای داخلی سرور</h1>
        <p><strong>خطا:</strong> {str(e)}</p>
        <details>
            <summary>جزئیات خطا (برای توسعه‌دهندگان)</summary>
            <pre>{error_traceback}</pre>
        </details>
        <p><a href="/admin">بازگشت به پنل مدیریت</a></p>
    </div>
</body>
</html>"""
    return Response(error_html, status=500, mimetype='text/html; charset=utf-8')


@admin_bp.route('/')
@login_required
@admin_required
def index():
    """Admin panel dashboard"""
    try:
        log_action('view_admin_panel')
    except Exception as e:
        logger.error(f"Error logging action: {e}")
    
    try:
        # Get statistics
        stats = {
            'total_users': User.query.count(),
            'total_dashboards': len(DashboardRegistry.list_all()),
            'total_access_logs': AccessLog.query.count(),
            'active_data_syncs': DataSync.query.filter_by(auto_sync_enabled=True).count(),
        }
        
        # Recent access logs
        recent_logs = AccessLog.query.order_by(AccessLog.created_at.desc()).limit(10).all()
        
        # Data sync status
        data_syncs = DataSync.query.all()
        
        return render_template('admin/index.html', 
                             stats=stats, 
                             recent_logs=recent_logs,
                             data_syncs=data_syncs)
    except Exception as e:
        logger.error(f"Error in admin index: {e}", exc_info=True)
        flash(f'خطا در بارگذاری پنل مدیریت: {str(e)}', 'error')
        return render_template('admin/index.html', 
                             stats={'total_users': 0, 'total_dashboards': 0, 'total_access_logs': 0, 'active_data_syncs': 0}, 
                             recent_logs=[],
                             data_syncs=[])


# ==================== User Management ====================

@admin_bp.route('/users')
@login_required
@admin_required
def users_list():
    """List all users"""
    log_action('view_users_list')
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '')
    
    query = User.query
    
    if search:
        query = query.filter(
            or_(
                User.name.contains(search),
                User.sso_id.contains(search),
                User.email.contains(search)
            )
        )
    
    users = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/users/list.html', users=users, search=search)


@admin_bp.route('/users/<int:user_id>')
@login_required
@admin_required
def user_detail(user_id):
    """View user details"""
    user = User.query.get_or_404(user_id)
    log_action('view_user', 'user', user_id)
    
    # Get user's dashboard accesses
    dashboard_accesses = DashboardAccess.query.filter_by(user_id=user_id).all()
    
    # Get user's recent access logs
    recent_logs = AccessLog.query.filter_by(user_id=user_id)\
        .order_by(AccessLog.created_at.desc()).limit(20).all()
    
    # Get organizational context
    org_context = get_user_org_context(user)
    
    return render_template('admin/users/detail.html', 
                         user=user, 
                         dashboard_accesses=dashboard_accesses,
                         recent_logs=recent_logs,
                         org_context=org_context)


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def user_edit(user_id):
    """Edit user"""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        # Update user fields
        user.name = request.form.get('name', user.name)
        user.email = request.form.get('email', user.email)
        user.province_code = request.form.get('province_code', type=int) or None
        user.university_code = request.form.get('university_code', type=int) or None
        user.faculty_code = request.form.get('faculty_code', type=int) or None
        
        # Update access levels
        access_levels = request.form.getlist('access_levels')
        # Remove existing access levels
        user.access_levels = []
        # Add new access levels
        for level in access_levels:
            if level:
                access = AccessLevelModel(level=level, user_id=user.id)
                db.session.add(access)
        
        db.session.commit()
        log_action('modify_user', 'user', user_id, {'changes': request.form.to_dict()})
        flash('کاربر با موفقیت به‌روزرسانی شد', 'success')
        return redirect(url_for('admin.user_detail', user_id=user_id))
    
    return render_template('admin/users/edit.html', user=user)


@admin_bp.route('/users/new', methods=['GET', 'POST'])
@login_required
@admin_required
def user_create():
    """Create new user"""
    if request.method == 'POST':
        sso_id = request.form.get('sso_id')
        if User.query.filter_by(sso_id=sso_id).first():
            flash('کاربری با این SSO ID وجود دارد', 'error')
            return render_template('admin/users/create.html')
        
        user = User(
            sso_id=sso_id,
            name=request.form.get('name'),
            email=request.form.get('email'),
            province_code=request.form.get('province_code', type=int) or None,
            university_code=request.form.get('university_code', type=int) or None,
            faculty_code=request.form.get('faculty_code', type=int) or None,
        )
        db.session.add(user)
        db.session.flush()
        
        # Add access levels
        access_levels = request.form.getlist('access_levels')
        for level in access_levels:
            if level:
                access = AccessLevelModel(level=level, user_id=user.id)
                db.session.add(access)
        
        db.session.commit()
        log_action('create_user', 'user', user.id)
        flash('کاربر با موفقیت ایجاد شد', 'success')
        return redirect(url_for('admin.user_detail', user_id=user.id))
    
    return render_template('admin/users/create.html')


# ==================== Dashboard Access Management ====================

@admin_bp.route('/dashboard-access')
@login_required
@admin_required
def dashboard_access_list():
    """List dashboard accesses"""
    log_action('view_dashboard_access_list')
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # Get filter parameters
    dashboard_id_filter = request.args.get('dashboard_id', '')
    user_id_filter = request.args.get('user_id', '')
    
    # Build query with filters
    query = DashboardAccess.query
    
    if dashboard_id_filter:
        query = query.filter(DashboardAccess.dashboard_id == dashboard_id_filter)
    
    if user_id_filter:
        try:
            user_id = int(user_id_filter)
            query = query.filter(DashboardAccess.user_id == user_id)
        except ValueError:
            pass
    
    # Get all accesses with pagination
    accesses = query.order_by(DashboardAccess.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Get all dashboards for filter dropdown
    dashboard_configs = {cfg.dashboard_id: cfg for cfg in DashboardConfig.query.all()}
    
    # Get all users for filter dropdown
    users = User.query.order_by(User.name).all()
    
    # Get unique dashboard IDs from accesses for filter dropdown
    unique_dashboard_ids = db.session.query(DashboardAccess.dashboard_id).distinct().all()
    unique_dashboard_ids = [d[0] for d in unique_dashboard_ids]
    
    return render_template('admin/dashboard_access/list.html', 
                         accesses=accesses,
                         dashboard_configs=dashboard_configs,
                         users=users,
                         unique_dashboard_ids=unique_dashboard_ids,
                         current_dashboard_filter=dashboard_id_filter,
                         current_user_filter=user_id_filter)


@admin_bp.route('/dashboard-access/new', methods=['GET', 'POST'])
@login_required
@admin_required
def dashboard_access_create():
    """Create dashboard access"""
    if request.method == 'POST':
        # Build filter restrictions from individual fields
        filter_restrictions = {}
        
        # Get province codes
        province_codes = request.form.getlist('province_codes')
        if province_codes:
            try:
                filter_restrictions['province_codes'] = [int(code) for code in province_codes if code]
            except (ValueError, TypeError):
                pass
        
        # Get university codes
        university_codes = request.form.getlist('university_codes')
        if university_codes:
            try:
                filter_restrictions['university_codes'] = [int(code) for code in university_codes if code]
            except (ValueError, TypeError):
                pass
        
        # Get faculty codes
        faculty_codes = request.form.getlist('faculty_codes')
        if faculty_codes:
            try:
                filter_restrictions['faculty_codes'] = [int(code) for code in faculty_codes if code]
            except (ValueError, TypeError):
                pass
        
        # If JSON is provided directly (for backward compatibility), use it
        filter_restrictions_json = request.form.get('filter_restrictions')
        if filter_restrictions_json:
            try:
                import json
                json_restrictions = json.loads(filter_restrictions_json)
                if json_restrictions:
                    filter_restrictions = json_restrictions
            except (json.JSONDecodeError, TypeError):
                pass
        
        access = DashboardAccess(
            user_id=request.form.get('user_id', type=int),
            dashboard_id=request.form.get('dashboard_id'),
            can_access=request.form.get('can_access') == 'on',
            filter_restrictions=filter_restrictions if filter_restrictions else {},
            created_by=current_user.id
        )
        
        # Parse Persian calendar date restrictions
        if request.form.get('date_from'):
            date_from_str = request.form.get('date_from').strip()
            if date_from_str:
                try:
                    # Parse Persian calendar date (format: YYYY/MM/DD)
                    date_parts = list(map(int, date_from_str.split('/')))
                    if len(date_parts) == 3:
                        jd = jdatetime.datetime(date_parts[0], date_parts[1], date_parts[2])
                        access.date_from = jd.togregorian()
                except (ValueError, IndexError, AttributeError) as e:
                    logger.error(f"Error parsing date_from: {e}")
        
        if request.form.get('date_to'):
            date_to_str = request.form.get('date_to').strip()
            if date_to_str:
                try:
                    # Parse Persian calendar date (format: YYYY/MM/DD)
                    date_parts = list(map(int, date_to_str.split('/')))
                    if len(date_parts) == 3:
                        jd = jdatetime.datetime(date_parts[0], date_parts[1], date_parts[2], 23, 59, 59)
                        access.date_to = jd.togregorian()
                except (ValueError, IndexError, AttributeError) as e:
                    logger.error(f"Error parsing date_to: {e}")
        
        db.session.add(access)
        db.session.commit()
        log_action('create_dashboard_access', 'dashboard_access', access.id)
        flash('دسترسی با موفقیت ایجاد شد', 'success')
        return redirect(url_for('admin.dashboard_access_list'))
    
    # Get available dashboards
    dashboards = DashboardRegistry.list_all()
    users = User.query.all()
    
    return render_template('admin/dashboard_access/create.html', 
                         dashboards=dashboards, 
                         users=users)


@admin_bp.route('/dashboard-access/<int:access_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def dashboard_access_edit(access_id):
    """Edit dashboard access"""
    access = DashboardAccess.query.get_or_404(access_id)
    
    if request.method == 'POST':
        access.can_access = request.form.get('can_access') == 'on'
        
        # Build filter restrictions from individual fields
        filter_restrictions = {}
        
        # Get province codes
        province_codes = request.form.getlist('province_codes')
        if province_codes:
            try:
                filter_restrictions['province_codes'] = [int(code) for code in province_codes if code]
            except (ValueError, TypeError):
                pass
        
        # Get university codes
        university_codes = request.form.getlist('university_codes')
        if university_codes:
            try:
                filter_restrictions['university_codes'] = [int(code) for code in university_codes if code]
            except (ValueError, TypeError):
                pass
        
        # Get faculty codes
        faculty_codes = request.form.getlist('faculty_codes')
        if faculty_codes:
            try:
                filter_restrictions['faculty_codes'] = [int(code) for code in faculty_codes if code]
            except (ValueError, TypeError):
                pass
        
        # If JSON is provided directly (for backward compatibility), use it
        filter_restrictions_json = request.form.get('filter_restrictions')
        if filter_restrictions_json:
            try:
                import json
                json_restrictions = json.loads(filter_restrictions_json)
                if json_restrictions:
                    filter_restrictions = json_restrictions
            except (json.JSONDecodeError, TypeError):
                pass
        
        access.filter_restrictions = filter_restrictions if filter_restrictions else {}
        
        # Parse Persian calendar date restrictions
        if request.form.get('date_from'):
            date_from_str = request.form.get('date_from').strip()
            if date_from_str:
                try:
                    # Parse Persian calendar date (format: YYYY/MM/DD)
                    date_parts = list(map(int, date_from_str.split('/')))
                    if len(date_parts) == 3:
                        jd = jdatetime.datetime(date_parts[0], date_parts[1], date_parts[2])
                        access.date_from = jd.togregorian()
                    else:
                        access.date_from = None
                except (ValueError, IndexError, AttributeError) as e:
                    logger.error(f"Error parsing date_from: {e}")
                    access.date_from = None
            else:
                access.date_from = None
        else:
            access.date_from = None
        
        if request.form.get('date_to'):
            date_to_str = request.form.get('date_to').strip()
            if date_to_str:
                try:
                    # Parse Persian calendar date (format: YYYY/MM/DD)
                    date_parts = list(map(int, date_to_str.split('/')))
                    if len(date_parts) == 3:
                        jd = jdatetime.datetime(date_parts[0], date_parts[1], date_parts[2], 23, 59, 59)
                        access.date_to = jd.togregorian()
                    else:
                        access.date_to = None
                except (ValueError, IndexError, AttributeError) as e:
                    logger.error(f"Error parsing date_to: {e}")
                    access.date_to = None
            else:
                access.date_to = None
        else:
            access.date_to = None
        
        db.session.commit()
        log_action('modify_dashboard_access', 'dashboard_access', access_id)
        flash('دسترسی با موفقیت به‌روزرسانی شد', 'success')
        return redirect(url_for('admin.dashboard_access_list'))
    
    dashboards = DashboardRegistry.list_all()
    users = User.query.all()
    
    # Convert dates to Persian calendar for display
    date_from_jalali = None
    date_to_jalali = None
    if access.date_from:
        try:
            date_from_jalali = jdatetime.datetime.fromgregorian(datetime=access.date_from).strftime('%Y/%m/%d')
        except:
            pass
    if access.date_to:
        try:
            date_to_jalali = jdatetime.datetime.fromgregorian(datetime=access.date_to).strftime('%Y/%m/%d')
        except:
            pass
    
    return render_template('admin/dashboard_access/edit.html', 
                         access=access, 
                         dashboards=dashboards, 
                         users=users,
                         date_from_jalali=date_from_jalali,
                         date_to_jalali=date_to_jalali)


# ==================== Access Logs ====================

@admin_bp.route('/logs')
@login_required
@admin_required
def logs_list():
    """List access logs"""
    log_action('view_access_logs')
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    user_id = request.args.get('user_id', type=int)
    action = request.args.get('action', '')
    
    query = AccessLog.query
    
    if user_id:
        query = query.filter_by(user_id=user_id)
    if action:
        query = query.filter_by(action=action)
    
    logs = query.order_by(AccessLog.created_at.desc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/logs/list.html', logs=logs, user_id=user_id, action=action)


# ==================== Data Sync Management ====================

@admin_bp.route('/data-sync/test')
@login_required
@admin_required
def data_sync_test():
    """Test endpoint to debug data sync issues"""
    import traceback
    try:
        from flask import jsonify
        result = {
            'status': 'ok',
            'data_sync_count': 0,
            'errors': [],
            'traceback': None
        }
        
        try:
            logger.info("Test endpoint: Querying DataSync...")
            syncs = DataSync.query.all()
            result['data_sync_count'] = len(syncs)
            result['syncs'] = []
            for sync in syncs:
                try:
                    sync_data = {
                        'id': sync.id,
                        'data_source': sync.data_source,
                        'status': sync.status,
                        'has_interval_value': hasattr(sync, 'sync_interval_value'),
                        'has_interval_unit': hasattr(sync, 'sync_interval_unit'),
                    }
                    try:
                        sync_data['interval_display'] = sync.get_interval_display()
                    except Exception as e:
                        sync_data['interval_display_error'] = str(e)
                        sync_data['interval_display_traceback'] = traceback.format_exc()
                    result['syncs'].append(sync_data)
                except Exception as e:
                    error_msg = f"Error processing sync {getattr(sync, 'id', 'unknown')}: {str(e)}"
                    result['errors'].append(error_msg)
                    logger.error(error_msg, exc_info=True)
        except Exception as e:
            error_msg = f"Error querying DataSync: {str(e)}"
            result['errors'].append(error_msg)
            result['traceback'] = traceback.format_exc()
            result['status'] = 'error'
            logger.error(error_msg, exc_info=True)
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Fatal error in test endpoint: {e}", exc_info=True)
        return jsonify({
            'status': 'error', 
            'message': str(e),
            'traceback': traceback.format_exc()
        }), 500


@admin_bp.route('/data-sync')
@login_required
@admin_required
def data_sync_list():
    """List data syncs"""
    import traceback
    from flask import Response
    
    try:
        logger.info("=" * 50)
        logger.info("Starting data_sync_list route")
        logger.info("=" * 50)
        
        # Try to log action (non-critical)
        try:
            log_action('view_data_syncs')
        except Exception as log_err:
            logger.warning(f"Error logging action: {log_err}")
        
        # Query syncs with error handling
        syncs = []
        try:
            logger.info("Querying DataSync table...")
            all_syncs = DataSync.query.order_by(DataSync.data_source).all()
            logger.info(f"Found {len(all_syncs)} syncs in database")
            
            # Validate each sync object
            validated_syncs = []
            for sync in all_syncs:
                try:
                    # Test if we can access key attributes
                    data_source = sync.data_source
                    status = sync.status
                    interval_value = getattr(sync, 'sync_interval_value', 60)
                    interval_unit = getattr(sync, 'sync_interval_unit', 'minutes')
                    
                    # Test methods
                    try:
                        interval_display = sync.get_interval_display()
                        logger.debug(f"Sync {sync.id}: interval_display = {interval_display}")
                    except Exception as method_err:
                        logger.warning(f"Error calling get_interval_display on sync {sync.id}: {method_err}")
                    
                    validated_syncs.append(sync)
                except Exception as sync_err:
                    logger.error(f"Error validating sync {getattr(sync, 'id', 'unknown')}: {sync_err}", exc_info=True)
                    continue
            syncs = validated_syncs
            logger.info(f"Validated {len(syncs)} syncs")
        except Exception as query_err:
            logger.error(f"Error querying DataSync: {query_err}", exc_info=True)
            logger.error(f"Query error traceback: {traceback.format_exc()}")
            syncs = []
        
        # Check scheduler status
        scheduler_running = False
        try:
            from .scheduler import is_scheduler_running
            scheduler_running = is_scheduler_running()
            logger.info(f"Scheduler running: {scheduler_running}")
        except Exception as e:
            logger.error(f"Error checking scheduler status: {e}", exc_info=True)
            scheduler_running = False
        
        # Render template
        logger.info(f"Rendering template with {len(syncs)} syncs")
        try:
            # Ensure all sync objects are properly initialized
            for sync in syncs:
                # Pre-call methods to catch any errors before template rendering
                try:
                    _ = sync.get_interval_display()
                except Exception as pre_err:
                    logger.warning(f"Pre-check failed for sync {sync.id}: {pre_err}")
            
            result = render_template('admin/data_sync/list.html', syncs=syncs, scheduler_running=scheduler_running)
            logger.info("Template rendered successfully")
            return result
        except Exception as template_err:
            logger.error(f"Error rendering template: {template_err}", exc_info=True)
            logger.error(f"Template error traceback: {traceback.format_exc()}")
            # Try to render a simple error page
            try:
                flash(f'خطا در نمایش لیست همگام‌سازی‌ها: {str(template_err)}', 'error')
                return render_template('admin/data_sync/list.html', syncs=[], scheduler_running=False)
            except Exception as render_err2:
                logger.error(f"Error rendering error page: {render_err2}", exc_info=True)
                from flask import Response
                error_html = f"""
                <html>
                <head><meta charset="utf-8"><title>خطا</title></head>
                <body dir="rtl">
                    <h1>خطای داخلی سرور</h1>
                    <h2>خطا در رندر کردن template:</h2>
                    <pre>{str(template_err)}</pre>
                    <h2>Traceback:</h2>
                    <pre>{traceback.format_exc()}</pre>
                </body>
                </html>
                """
                return Response(error_html, status=500, mimetype='text/html; charset=utf-8')
        
    except Exception as e:
        error_traceback = traceback.format_exc()
        logger.error("=" * 50)
        logger.error(f"FATAL ERROR in data_sync_list: {e}")
        logger.error("=" * 50)
        logger.error(f"Full traceback:\n{error_traceback}")
        logger.error("=" * 50)
        
        try:
            flash(f'خطا در نمایش لیست همگام‌سازی‌ها: {str(e)}', 'error')
            return render_template('admin/data_sync/list.html', syncs=[], scheduler_running=False)
        except Exception as render_err:
            logger.error(f"Error rendering error page: {render_err}", exc_info=True)
            error_html = f"""<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
    <meta charset="utf-8">
    <title>خطای سرور</title>
    <style>
        body {{ font-family: Tahoma, Arial; padding: 20px; background: #f5f5f5; }}
        .error-box {{ background: white; padding: 20px; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        h1 {{ color: #d32f2f; }}
        pre {{ background: #f5f5f5; padding: 10px; border-radius: 3px; overflow-x: auto; }}
    </style>
</head>
<body>
    <div class="error-box">
        <h1>خطای داخلی سرور</h1>
        <h2>خطا:</h2>
        <pre>{str(e)}</pre>
        <h2>Traceback:</h2>
        <pre>{error_traceback}</pre>
    </div>
</body>
</html>"""
            return Response(error_html, status=500, mimetype='text/html; charset=utf-8')


@admin_bp.route('/data-sync/<int:sync_id>/sync', methods=['POST'])
@login_required
@admin_required
def data_sync_trigger(sync_id):
    """Trigger manual data sync in background"""
    sync = DataSync.query.get_or_404(sync_id)
    
    # For LMS sync, always perform manual sync (stops continuous sync first)
    if sync.data_source == 'lms':
        log_action('trigger_data_sync', 'data_sync', sync_id, {'data_source': sync.data_source, 'manual': True})
        
        # Import sync handler
        from .sync_handlers import run_lms_sync
        import threading
        from flask import current_app
        
        def run_manual_sync_background():
            """Run manual LMS sync in background thread (will stop continuous sync first)"""
            try:
                with current_app.app_context():
                    run_lms_sync(user_id=current_user.id, sync_id=sync_id, manual_sync=True)
            except Exception as e:
                logger.error(f"Error in background manual sync: {e}", exc_info=True)
        
        # Start manual sync in background thread
        thread = threading.Thread(target=run_manual_sync_background, daemon=True)
        thread.start()
        
        flash('همگام‌سازی دستی LMS شروع شد. در صورت فعال بودن، همگام‌سازی مداوم متوقف و پس از اتمام، دوباره شروع می‌شود.', 'info')
        return redirect(url_for('admin.data_sync_list'))
    
    # Check if sync is already running (for non-LMS syncs)
    if sync.status == 'running':
        flash('همگام‌سازی در حال اجرا است. لطفاً منتظر بمانید.', 'warning')
        return redirect(url_for('admin.data_sync_list'))
    
    log_action('trigger_data_sync', 'data_sync', sync_id, {'data_source': sync.data_source})
    
    # Import sync handler
    from .sync_handlers import run_sync_by_source
    import threading
    from flask import current_app
    
    def run_sync_background():
        """Run sync in background thread"""
        try:
            with current_app.app_context():
                run_sync_by_source(sync.data_source, current_user.id, sync_id=sync_id)
        except Exception as e:
            logger.error(f"Error in background sync: {e}", exc_info=True)
    
    # Start sync in background thread
    thread = threading.Thread(target=run_sync_background, daemon=True)
    thread.start()
    
    flash('همگام‌سازی شروع شد. وضعیت را در جدول زیر مشاهده کنید.', 'info')
    return redirect(url_for('admin.data_sync_list'))


@admin_bp.route('/data-sync/<int:sync_id>/stop', methods=['POST'])
@login_required
@admin_required
def data_sync_stop(sync_id):
    """Stop a running sync"""
    sync = DataSync.query.get_or_404(sync_id)
    
    # For LMS continuous sync, check both status and thread status
    # Allow stopping if either status is 'running' or thread is actually running
    can_stop = False
    if sync.data_source == 'lms':
        from .sync_handlers import _lms_continuous_thread, _lms_continuous_running
        thread_is_alive = _lms_continuous_thread and _lms_continuous_thread.is_alive()
        can_stop = sync.status == 'running' or _lms_continuous_running or thread_is_alive
    else:
        can_stop = sync.status == 'running'
    
    if not can_stop:
        flash('همگام‌سازی در حال اجرا نیست.', 'warning')
        return redirect(url_for('admin.data_sync_list'))
    
    log_action('stop_data_sync', 'data_sync', sync_id, {'data_source': sync.data_source})
    
    # Import sync handler
    from .sync_handlers import stop_sync_by_source
    
    success, message = stop_sync_by_source(sync.data_source, sync_id=sync_id)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    return redirect(url_for('admin.data_sync_list'))


@admin_bp.route('/data-sync/<int:sync_id>/restart', methods=['POST'])
@login_required
@admin_required
def data_sync_restart(sync_id):
    """Restart a sync (stop if running, then start)"""
    sync = DataSync.query.get_or_404(sync_id)
    
    log_action('restart_data_sync', 'data_sync', sync_id, {'data_source': sync.data_source})
    
    # Import sync handlers
    from .sync_handlers import stop_sync_by_source, run_sync_by_source
    import threading
    from flask import current_app
    
    # Stop if running
    if sync.status == 'running':
        stop_sync_by_source(sync.data_source, sync_id=sync_id)
        import time
        time.sleep(1)  # Wait a bit for stop to complete
    
    # Start sync in background thread
    def run_sync_background():
        """Run sync in background thread"""
        try:
            with current_app.app_context():
                run_sync_by_source(sync.data_source, current_user.id, sync_id=sync_id)
        except Exception as e:
            logger.error(f"Error in background sync: {e}", exc_info=True)
    
    thread = threading.Thread(target=run_sync_background, daemon=True)
    thread.start()
    
    flash('همگام‌سازی دوباره راه‌اندازی شد.', 'success')
    return redirect(url_for('admin.data_sync_list'))


@admin_bp.route('/scheduler/start', methods=['POST'])
@login_required
@admin_required
def scheduler_start():
    """Start the auto-sync scheduler"""
    try:
        from .scheduler import start_scheduler, is_scheduler_running
        
        if is_scheduler_running():
            flash('Scheduler در حال اجرا است.', 'info')
        else:
            start_scheduler()
            log_action('start_scheduler', 'system', None, {})
            flash('Scheduler با موفقیت شروع شد.', 'success')
    except Exception as e:
        logger.error(f"Error starting scheduler: {e}", exc_info=True)
        flash(f'خطا در شروع Scheduler: {str(e)}', 'error')
    
    return redirect(url_for('admin.data_sync_list'))


@admin_bp.route('/scheduler/stop', methods=['POST'])
@login_required
@admin_required
def scheduler_stop():
    """Stop the auto-sync scheduler"""
    try:
        from .scheduler import stop_scheduler, is_scheduler_running
        
        if not is_scheduler_running():
            flash('Scheduler در حال اجرا نیست.', 'info')
        else:
            stop_scheduler()
            log_action('stop_scheduler', 'system', None, {})
            flash('Scheduler با موفقیت متوقف شد.', 'success')
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}", exc_info=True)
        flash(f'خطا در توقف Scheduler: {str(e)}', 'error')
    
    return redirect(url_for('admin.data_sync_list'))


@admin_bp.route('/data-sync/<int:sync_id>/progress')
@login_required
@admin_required
def data_sync_progress(sync_id):
    """Get real-time progress of sync operation"""
    from .sync_progress import get_sync_progress
    
    progress = get_sync_progress(sync_id)
    
    if not progress:
        # Check database status
        sync = DataSync.query.get_or_404(sync_id)
        return jsonify({
            'status': sync.status,
            'progress': 100 if sync.status in ['success', 'failed'] else 0,
            'current_step': sync.status,
            'records_processed': sync.records_synced,
            'error_message': sync.error_message,
            'logs': []
        })
    
    return jsonify(progress)


@admin_bp.route('/data-sync/logs')
@login_required
@admin_required
def sync_logs():
    """View auto-sync logs"""
    log_action('view_sync_logs')
    
    # Get logs related to auto-sync
    logs = AccessLog.query.filter(
        AccessLog.action.in_(['auto_sync_started', 'auto_sync_completed', 'auto_sync_failed', 'auto_sync_error'])
    ).order_by(AccessLog.created_at.desc()).limit(100).all()
    
    return render_template('admin/data_sync/logs.html', logs=logs)


@admin_bp.route('/data-sync/<int:sync_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def data_sync_edit(sync_id):
    """Edit data sync configuration"""
    sync = DataSync.query.get_or_404(sync_id)
    
    if request.method == 'POST':
        # Validate required fields
        api_endpoint = request.form.get('api_endpoint', '').strip()
        if not api_endpoint:
            flash('لطفاً API Endpoint را وارد کنید', 'error')
            return render_template('admin/data_sync/edit.html', sync=sync)
        
        sync.auto_sync_enabled = request.form.get('auto_sync_enabled') == 'on'
        sync.sync_interval_value = request.form.get('sync_interval_value', type=int) or 60
        sync.sync_interval_unit = request.form.get('sync_interval_unit', 'minutes')
        sync.api_base_url = request.form.get('api_base_url', '').strip() or None
        sync.api_endpoint = api_endpoint
        sync.api_method = request.form.get('api_method', 'GET')
        sync.api_username = request.form.get('api_username', '').strip() or None
        # Only update password if provided (to allow keeping existing password)
        api_password = request.form.get('api_password', '').strip()
        if api_password:
            sync.api_password = api_password
        
        # Calculate next sync time
        if sync.auto_sync_enabled and sync.last_sync_at:
            interval_minutes = sync.get_interval_minutes()
            sync.next_sync_at = sync.last_sync_at + timedelta(minutes=interval_minutes)
        elif not sync.auto_sync_enabled:
            sync.next_sync_at = None
        
        db.session.commit()
        log_action('modify_data_sync', 'data_sync', sync_id, {
            'auto_sync_enabled': sync.auto_sync_enabled,
            'sync_interval_value': sync.sync_interval_value,
            'sync_interval_unit': sync.sync_interval_unit,
            'api_endpoint': sync.api_endpoint,
            'api_method': sync.api_method
        })
        flash('تنظیمات همگام‌سازی با موفقیت به‌روزرسانی شد', 'success')
        return redirect(url_for('admin.data_sync_list'))
    
    return render_template('admin/data_sync/edit.html', sync=sync)


@admin_bp.route('/data-sync/<int:sync_id>/test-connection', methods=['POST'])
@login_required
@admin_required
def test_api_connection(sync_id):
    """Test API connection for a sync configuration"""
    sync = DataSync.query.get_or_404(sync_id)
    
    try:
        import requests
        
        # Get values from form data (if provided) or use sync object values
        api_base_url = request.form.get('api_base_url', '').strip() or sync.api_base_url
        api_endpoint = request.form.get('api_endpoint', '').strip() or sync.api_endpoint
        api_username = request.form.get('api_username', '').strip() or sync.api_username
        
        # Handle password: if form password is empty, use sync password
        form_password = request.form.get('api_password', '').strip()
        api_password = form_password if form_password else (sync.api_password or '')
        
        # Log for debugging
        logger.info(f"Test connection - Base URL: {api_base_url}, Endpoint: {api_endpoint}, Username: {api_username}, Password provided: {bool(api_password)}")
        
        # For faculty and students, test login first
        if sync.data_source in ['faculty', 'students']:
            if not api_base_url or not api_username or not api_password:
                missing_fields = []
                if not api_base_url:
                    missing_fields.append('Base URL')
                if not api_username:
                    missing_fields.append('Username')
                if not api_password:
                    missing_fields.append('Password')
                return jsonify({
                    'success': False,
                    'message': f'اطلاعات احراز هویت کامل نیست. فیلدهای خالی: {", ".join(missing_fields)}'
                }), 400
            
            # Test login
            login_url = f"{api_base_url}/Login"
            login_payload = {
                "userName": api_username,
                "password": api_password
            }
            
            try:
                response = requests.post(login_url, json=login_payload, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                if 'data' not in data or 'token' not in data['data']:
                    return jsonify({
                        'success': False,
                        'message': 'خطا در دریافت Token: پاسخ API نامعتبر است'
                    }), 400
                
                token = data['data']['token']
                
                # Test endpoint with token
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                
                # Build proper test payload based on data source
                if sync.data_source == 'students':
                    # Students API requires codePardis, term, paging, and Filter
                    # Try to get a valid pardis_code from database
                    try:
                        import sqlite3
                        import os
                        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                        db_path = os.path.join(BASE_DIR, 'access_control.db')
                        if os.path.exists(db_path):
                            conn = sqlite3.connect(db_path)
                            cursor = conn.cursor()
                            cursor.execute("SELECT pardis_code FROM pardis LIMIT 1")
                            row = cursor.fetchone()
                            conn.close()
                            test_pardis = str(row[0]) if row else "1110"  # Default to a known valid code
                        else:
                            test_pardis = "1110"  # Default to a known valid code
                    except Exception as db_err:
                        logger.warning(f"Could not read pardis_code from DB: {db_err}")
                        test_pardis = "1110"  # Default to a known valid code
                    
                    # Use a valid term format
                    # Term format: last 3 digits of year + term number
                    # e.g., year 1400 -> 400, term 1 -> 4001
                    # e.g., year 1404 -> 404, term 1 -> 4041
                    # Use a recent term (1404, term 1 = 4041)
                    # Make sure codePardis and term are strings
                    test_payload = {
                        "codePardis": str(test_pardis).strip(),
                        "term": "4041",  # Year 1404, Term 1 (more likely to have data)
                        "paging": {
                            "pageNumber": 1,
                            "pageSize": 1
                        },
                        "Filter": {}
                    }
                    
                    # Validate payload before sending
                    if not test_payload["codePardis"] or not test_payload["term"]:
                        return jsonify({
                            'success': False,
                            'message': f'خطا در ساخت payload: codePardis={test_payload["codePardis"]}, term={test_payload["term"]}'
                        }), 400
                elif sync.data_source == 'faculty':
                    # Faculty API only requires paging
                    test_payload = {
                        "pageNumber": 1,
                        "pageSize": 1
                    }
                else:
                    test_payload = {"pageNumber": 1, "pageSize": 1}
                
                # Log the request for debugging
                logger.info(f"Testing API connection for {sync.data_source}")
                logger.info(f"Endpoint: {api_endpoint}")
                logger.info(f"Payload: {test_payload}")
                logger.info(f"Headers: {headers}")
                
                endpoint_response = requests.post(
                    api_endpoint,
                    json=test_payload,
                    headers=headers,
                    timeout=10
                )
                
                # Log response for debugging
                logger.info(f"Response status: {endpoint_response.status_code}")
                logger.info(f"Response headers: {dict(endpoint_response.headers)}")
                logger.info(f"Response text (first 1000 chars): {endpoint_response.text[:1000]}")
                
                # Check status before raising
                if endpoint_response.status_code != 200:
                    # Try to parse error response
                    try:
                        error_data = endpoint_response.json()
                        logger.error(f"API Error Response: {error_data}")
                    except:
                        logger.error(f"API Error Response (raw): {endpoint_response.text}")
                
                endpoint_response.raise_for_status()
                
                return jsonify({
                    'success': True,
                    'message': f'اتصال موفق! Token دریافت شد و endpoint پاسخ داد. (Status: {endpoint_response.status_code})'
                })
                
            except requests.exceptions.Timeout:
                return jsonify({
                    'success': False,
                    'message': 'Timeout: سرور پاسخ نداد. لطفاً اتصال اینترنت و آدرس API را بررسی کنید.'
                }), 400
            except requests.exceptions.ConnectionError:
                return jsonify({
                    'success': False,
                    'message': 'خطا در اتصال: نمی‌توان به سرور متصل شد. لطفاً آدرس API را بررسی کنید.'
                }), 400
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    return jsonify({
                        'success': False,
                        'message': 'خطا در احراز هویت: Username یا Password اشتباه است.'
                    }), 400
                else:
                    # Try to parse error response for better error message
                    error_msg = f'خطای HTTP {e.response.status_code}'
                    error_details = []
                    
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get('title', error_msg)
                        
                        # Extract validation errors if available
                        if 'errors' in error_data:
                            errors = error_data['errors']
                            if errors:
                                # errors can be a dict or a string or a list
                                if isinstance(errors, dict):
                                    for field, messages in errors.items():
                                        if isinstance(messages, list):
                                            error_details.append(f"{field}: {', '.join(str(m) for m in messages)}")
                                        else:
                                            error_details.append(f"{field}: {messages}")
                                elif isinstance(errors, str):
                                    error_details.append(f"خطا: {errors}")
                                elif isinstance(errors, list):
                                    error_details.append(f"خطاها: {', '.join(str(e) for e in errors)}")
                                else:
                                    error_details.append(f"خطاهای validation: {str(errors)}")
                            else:
                                # errors field exists but is empty/null
                                error_details.append("خطاهای validation (بدون جزئیات - فیلد errors خالی است)")
                        
                        # Also check for 'message' field
                        if 'message' in error_data and error_data['message']:
                            error_details.append(f"پیام: {error_data['message']}")
                        
                        # Include traceId if available for debugging
                        if 'traceId' in error_data:
                            error_details.append(f"TraceId: {error_data['traceId']}")
                        
                        # Include full error data for debugging
                        logger.error(f"Full error response: {error_data}")
                            
                    except Exception as parse_err:
                        # If JSON parsing fails, use raw text
                        error_text = e.response.text[:1000] if e.response.text else ''
                        error_details.append(f"پاسخ خام: {error_text}")
                        logger.error(f"Error parsing error response: {parse_err}")
                        logger.error(f"Raw response: {e.response.text}")
                    
                    full_message = error_msg
                    if error_details:
                        full_message += f" | جزئیات: {' | '.join(error_details)}"
                    else:
                        # If no details, include the raw response
                        try:
                            raw_error = e.response.json()
                            full_message += f" | پاسخ کامل: {str(raw_error)[:500]}"
                        except:
                            full_message += f" | پاسخ خام: {e.response.text[:500]}"
                    
                    return jsonify({
                        'success': False,
                        'message': full_message
                    }), 400
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': f'خطا: {str(e)}'
                }), 400
        
        # For LMS, just test endpoint accessibility
        elif sync.data_source == 'lms':
            if not api_endpoint:
                return jsonify({
                    'success': False,
                    'message': 'API Endpoint تعریف نشده است'
                }), 400
            
            try:
                response = requests.get(api_endpoint, timeout=10, verify=False)
                response.raise_for_status()
                return jsonify({
                    'success': True,
                    'message': f'اتصال موفق! Endpoint پاسخ داد. (Status: {response.status_code})'
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'message': f'خطا در اتصال: {str(e)}'
                }), 400
        
        else:
            return jsonify({
                'success': False,
                'message': 'نوع منبع داده پشتیبانی نشده برای تست'
            }), 400
            
    except Exception as e:
        logger.error(f"Error testing connection: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'خطای غیرمنتظره: {str(e)}'
        }), 500


# ==================== Dashboard Configuration ====================

@admin_bp.route('/dashboards')
@login_required
@admin_required
def dashboards_list():
    """List dashboard configurations"""
    log_action('view_dashboard_configs')
    
    # Get dashboards from registry
    registry_dashboards = DashboardRegistry.list_all()
    
    # Get configurations from database
    configs = {cfg.dashboard_id: cfg for cfg in DashboardConfig.query.all()}
    
    # Merge registry dashboards with configs
    dashboards = []
    for dashboard in registry_dashboards:
        config = configs.get(dashboard.dashboard_id)
        dashboards.append({
            'dashboard': dashboard,
            'config': config
        })
    
    return render_template('admin/dashboards/list.html', dashboards=dashboards)


@admin_bp.route('/debug/user-access/<sso_id>')
@login_required
@admin_required
def debug_user_access(sso_id):
    """Debug endpoint to check user dashboard access"""
    user = User.query.filter_by(sso_id=sso_id.lower()).first()
    if not user:
        return jsonify({"error": f"User with SSO ID '{sso_id}' not found"}), 404
    
    # Check admin status
    is_admin = user.is_admin()
    
    # Get dashboard access records
    dashboard_accesses = DashboardAccess.query.filter_by(user_id=user.id).all()
    
    # Get public dashboards
    public_dashboards = DashboardConfig.query.filter_by(is_public=True).all()
    
    # Try to create user context
    try:
        from dashboards.context import UserContext
        user_context = UserContext(user, {})
        access_level = user_context.access_level.value
    except Exception as e:
        access_level = f"Error: {str(e)}"
    
    result = {
        "user": {
            "id": user.id,
            "name": user.name,
            "sso_id": user.sso_id,
            "email": user.email,
            "is_admin": is_admin,
            "access_level": access_level,
            "access_levels": [acc.level for acc in user.access_levels]
        },
        "dashboard_accesses": [
            {
                "dashboard_id": acc.dashboard_id,
                "can_access": acc.can_access,
                "filter_restrictions": acc.filter_restrictions,
                "date_from": acc.date_from.isoformat() if acc.date_from else None,
                "date_to": acc.date_to.isoformat() if acc.date_to else None
            }
            for acc in dashboard_accesses
        ],
        "public_dashboards": [
            {
                "dashboard_id": cfg.dashboard_id,
                "title": cfg.title
            }
            for cfg in public_dashboards
        ],
        "summary": {
            "has_admin_access": is_admin,
            "has_explicit_access": len([a for a in dashboard_accesses if a.can_access]) > 0,
            "has_public_access": len(public_dashboards) > 0,
            "can_access_dashboards": is_admin or len([a for a in dashboard_accesses if a.can_access]) > 0 or len(public_dashboards) > 0
        }
    }
    
    return jsonify(result)


@admin_bp.route('/dashboards/<dashboard_id>/config', methods=['GET', 'POST'])
@login_required
@admin_required
def dashboard_config_edit(dashboard_id):
    """Edit dashboard configuration"""
    dashboard = DashboardRegistry.get(dashboard_id)
    if not dashboard:
        flash('داشبورد یافت نشد', 'error')
        return redirect(url_for('admin.dashboards_list'))
    
    config = DashboardConfig.query.filter_by(dashboard_id=dashboard_id).first()
    
    if request.method == 'POST':
        if not config:
            config = DashboardConfig(
                dashboard_id=dashboard_id,
                created_by=current_user.id
            )
            db.session.add(config)
        
        config.title = request.form.get('title', dashboard.title)
        config.description = request.form.get('description', dashboard.description or '')
        config.icon = request.form.get('icon')
        config.order = request.form.get('order', type=int) or 0
        config.is_active = request.form.get('is_active') == 'on'
        config.is_public = request.form.get('is_public') == 'on'
        config.cache_ttl_seconds = request.form.get('cache_ttl_seconds', type=int) or 300
        config.refresh_interval_seconds = request.form.get('refresh_interval_seconds', type=int) or None
        
        db.session.commit()
        log_action('modify_dashboard_config', 'dashboard', dashboard_id)
        flash('تنظیمات داشبورد با موفقیت به‌روزرسانی شد', 'success')
        return redirect(url_for('admin.dashboards_list'))
    
    return render_template('admin/dashboards/config.html', 
                         dashboard=dashboard, 
                         config=config)


# ==================== Dashboard Template Editing ====================

@admin_bp.route('/dashboards/templates')
@login_required
@admin_required
def dashboard_templates_list():
    """List all dashboard template files"""
    log_action('view_dashboard_templates')
    
    # Get template directory path
    base_dir = Path(__file__).parent.parent
    templates_dir = base_dir / 'templates' / 'dashboards'
    
    # Get all HTML files in dashboards directory
    templates = []
    if templates_dir.exists():
        for file_path in templates_dir.glob('*.html'):
            # Skip files starting with underscore (partial templates)
            if not file_path.name.startswith('_'):
                templates.append({
                    'name': file_path.name,
                    'size': file_path.stat().st_size,
                    'modified': datetime.fromtimestamp(file_path.stat().st_mtime),
                    'dashboard_id': file_path.stem  # filename without extension
                })
    
    # Sort by name
    templates.sort(key=lambda x: x['name'])
    
    # Get dashboards from registry to match with templates
    registry_dashboards = {d.dashboard_id: d for d in DashboardRegistry.list_all()}
    
    # Add dashboard info to templates
    for template in templates:
        dashboard_id = template['dashboard_id']
        template['dashboard'] = registry_dashboards.get(dashboard_id)
    
    return render_template('admin/dashboards/templates_list.html', templates=templates)


@admin_bp.route('/dashboards/templates/<template_name>')
@login_required
@admin_required
def dashboard_template_view(template_name):
    """View a dashboard template file"""
    # Wrap entire function to catch all errors - including decorator errors
    try:
        logger.info(f"dashboard_template_view called for: {template_name}")
        try:
            log_action('view_dashboard_template', 'template', template_name)
        except Exception as e:
            logger.warning(f"Error logging action: {e}")
        
        try:
            # Security: Only allow HTML files
            if not template_name.endswith('.html') or '..' in template_name or '/' in template_name:
                flash('نام فایل نامعتبر است', 'error')
                return redirect(url_for('admin.dashboard_templates_list'))
            
            # Get template directory path
            base_dir = Path(__file__).parent.parent
            template_path = base_dir / 'templates' / 'dashboards' / template_name
            
            if not template_path.exists():
                flash('تمپلیت یافت نشد', 'error')
                return redirect(url_for('admin.dashboard_templates_list'))
            
            # Read template content
            try:
                with open(template_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                logger.error(f"Error reading template {template_name}: {e}", exc_info=True)
                flash(f'خطا در خواندن فایل: {str(e)}', 'error')
                return redirect(url_for('admin.dashboard_templates_list'))
            
            # Get file info
            file_stat = None
            file_size = 0
            try:
                file_stat = template_path.stat()
                file_size = file_stat.st_size if file_stat else 0
            except Exception as e:
                logger.warning(f"Error getting file stats: {e}")
                file_size = 0
            
            dashboard_id = template_path.stem
            dashboard = None
            try:
                dashboard = DashboardRegistry.get(dashboard_id)
            except Exception as e:
                logger.warning(f"Could not get dashboard {dashboard_id} from registry: {e}")
            
            # Get file modification time safely
            modified_time = None
            try:
                if file_stat:
                    modified_time = datetime.fromtimestamp(file_stat.st_mtime)
            except (OSError, ValueError, AttributeError) as e:
                logger.warning(f"Error getting file modification time: {e}")
                modified_time = datetime.now()
            
            # Render template with error handling
            try:
                # Ensure file_size is a number
                if file_size is None:
                    file_size = 0
                file_size = float(file_size) if file_size else 0.0
                
                return render_template('admin/dashboards/template_edit.html',
                                     template_name=template_name,
                                     content=content,
                                     dashboard=dashboard,
                                     file_size=file_size,
                                     modified_time=modified_time)
            except Exception as render_err:
                logger.error(f"Error rendering template_edit.html for {template_name}: {render_err}", exc_info=True)
                import traceback
                error_traceback = traceback.format_exc()
                logger.error(f"Template render traceback: {error_traceback}")
                
                # Return error page
                from flask import Response
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
        <p><strong>خطا:</strong> {str(render_err)}</p>
        <details>
            <summary>جزئیات خطا (برای توسعه‌دهندگان)</summary>
            <pre>{error_traceback}</pre>
        </details>
        <p><a href="/admin/dashboards/templates">بازگشت به لیست تمپلیت‌ها</a></p>
    </div>
</body>
</html>"""
                return Response(error_html, status=500, mimetype='text/html; charset=utf-8')
            
        except Exception as e:
            logger.error(f"Fatal error in dashboard_template_view for {template_name}: {e}", exc_info=True)
            import traceback
            error_traceback = traceback.format_exc()
            logger.error(f"Fatal error traceback: {error_traceback}")
            
            from flask import Response
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
        <h1>خطای غیرمنتظره</h1>
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
    except Exception as e:
        logger.error(f"Fatal error in dashboard_template_view for {template_name}: {e}", exc_info=True)
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"Fatal error traceback: {error_traceback}")
        
        from flask import Response
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
        <h1>خطای غیرمنتظره</h1>
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


@admin_bp.route('/dashboards/templates/<template_name>/edit', methods=['POST'])
@login_required
@admin_required
def dashboard_template_save(template_name):
    """Save changes to a dashboard template file"""
    log_action('edit_dashboard_template', 'template', template_name)
    
    # Security: Only allow HTML files
    if not template_name.endswith('.html') or '..' in template_name or '/' in template_name:
        return jsonify({
            'success': False,
            'message': 'نام فایل نامعتبر است'
        }), 400
    
    # Get template directory path
    base_dir = Path(__file__).parent.parent
    template_path = base_dir / 'templates' / 'dashboards' / template_name
    
    if not template_path.exists():
        return jsonify({
            'success': False,
            'message': 'تمپلیت یافت نشد'
        }), 404
    
    # Get content from request
    if request.is_json:
        data = request.get_json()
        content = data.get('content', '')
    else:
        content = request.form.get('content', '')
    
    if not content:
        return jsonify({
            'success': False,
            'message': 'محتوای تمپلیت خالی است'
        }), 400
    
    # Create backup before saving
    try:
        backup_path = template_path.with_suffix('.html.backup')
        shutil.copy2(template_path, backup_path)
    except Exception as e:
        logger.warning(f"Could not create backup for {template_name}: {e}")
    
    # Save template
    try:
        with open(template_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Update modification time
        template_path.touch()
        
        logger.info(f"Template {template_name} updated by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'تمپلیت با موفقیت به‌روزرسانی شد',
            'modified_time': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error saving template {template_name}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'خطا در ذخیره فایل: {str(e)}'
        }), 500


@admin_bp.route('/dashboards/templates/<template_name>/preview', methods=['GET'])
@login_required
@admin_required
def dashboard_template_preview(template_name):
    """Preview a dashboard template (read-only view)"""
    log_action('preview_dashboard_template', 'template', template_name)
    
    # Security: Only allow HTML files
    if not template_name.endswith('.html') or '..' in template_name or '/' in template_name:
        flash('نام فایل نامعتبر است', 'error')
        return redirect(url_for('admin.dashboard_templates_list'))
    
    # Get template directory path
    base_dir = Path(__file__).parent.parent
    template_path = base_dir / 'templates' / 'dashboards' / template_name
    
    if not template_path.exists():
        flash('تمپلیت یافت نشد', 'error')
        return redirect(url_for('admin.dashboard_templates_list'))
    
    # Read template content
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        logger.error(f"Error reading template {template_name}: {e}", exc_info=True)
        flash(f'خطا در خواندن فایل: {str(e)}', 'error')
        return redirect(url_for('admin.dashboard_templates_list'))
    
    dashboard_id = template_path.stem
    
    return render_template('admin/dashboards/template_preview.html',
                         template_name=template_name,
                         content=content,
                         dashboard_id=dashboard_id)


# ==================== Chart Configuration API ====================

@admin_bp.route('/dashboards/templates/<template_name>/charts', methods=['GET'])
@login_required
@admin_required
def dashboard_template_charts(template_name):
    """Get chart configurations for a template"""
    try:
        log_action('view_chart_configs', 'template', template_name)
    except Exception as e:
        logger.warning(f"Error logging action: {e}")
    
    try:
        # Security check
        if not template_name.endswith('.html') or '..' in template_name or '/' in template_name:
            return jsonify({'success': False, 'message': 'نام فایل نامعتبر است'}), 400
        
        # Get template path
        base_dir = Path(__file__).parent.parent
        template_path = base_dir / 'templates' / 'dashboards' / template_name
        
        if not template_path.exists():
            return jsonify({'success': False, 'message': 'تمپلیت یافت نشد'}), 404
        
        # Read template content
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Error reading template {template_name}: {e}", exc_info=True)
            return jsonify({'success': False, 'message': f'خطا در خواندن فایل: {str(e)}'}), 500
        
        # Get dashboard_id from template name (e.g., 'd1.html' -> 'd1')
        dashboard_id = template_path.stem
        
        # Try to get actual data from dashboard
        dashboard_data = {}
        try:
            from dashboards.context import UserContext
            # Create admin context for full access
            admin_context = UserContext(current_user, {})
            admin_context.access_level = admin_context._determine_access_level()
            
            # Get dashboard from registry
            dashboard = DashboardRegistry.get(dashboard_id)
            if dashboard:
                # Get actual data from dashboard
                dashboard_data = dashboard.get_data(admin_context, filters={})
                logger.info(f"Retrieved actual data for dashboard {dashboard_id}")
        except Exception as e:
            logger.warning(f"Could not get actual data for dashboard {dashboard_id}: {e}")
            dashboard_data = {}
        
        # Parse charts from template
        import re
        charts = []
        
        # Find all canvas elements with id
        canvas_pattern = r'<canvas\s+id=["\']([^"\']+)["\']'
        canvas_matches = re.findall(canvas_pattern, content)
        
        # Find chart titles from HTML structure
        for chart_id in canvas_matches:
            title = None
            
            # Find the position of the canvas element
            canvas_pos = content.find(f'id="{chart_id}"')
            if canvas_pos == -1:
                canvas_pos = content.find(f"id='{chart_id}'")
            
            if canvas_pos > 0:
                # Get the content before the canvas
                before_canvas = content[:canvas_pos]
                
                # Method 1: Look for h3, h4, h5 before the canvas (most common pattern)
                # Search backwards from canvas position
                h_patterns = [
                    r'<h3[^>]*>([^<]+)</h3>',
                    r'<h4[^>]*>([^<]+)</h4>',
                    r'<h5[^>]*>([^<]+)</h5>',
                ]
                
                for pattern in h_patterns:
                    matches = list(re.finditer(pattern, before_canvas))
                    if matches:
                        # Get the last match before canvas (closest to canvas)
                        last_match = matches[-1]
                        # Check if it's reasonably close (within 500 characters)
                        if canvas_pos - last_match.end() < 500:
                            title = last_match.group(1).strip()
                            break
                
                # Method 2: Look for card-title class
                if not title:
                    title_pattern = r'<h[345][^>]*class=["\'][^"\']*card-title[^"\']*["\'][^>]*>([^<]+)</h[345]>'
                    title_match = re.search(title_pattern, before_canvas)
                    if title_match:
                        title = title_match.group(1).strip()
                
                # Method 3: Look for card-header
                if not title:
                    header_pattern = r'<div[^>]*class=["\'][^"\']*card-header[^"\']*["\'][^>]*>([^<]+)</div>'
                    header_match = re.search(header_pattern, before_canvas)
                    if header_match:
                        title = header_match.group(1).strip()
                
                # Method 4: Look for Chart.js title in options
                if not title:
                    # Search for Chart.js title configuration after the canvas
                    after_canvas = content[canvas_pos:canvas_pos + 2000]  # Look 2000 chars ahead
                    chart_title_patterns = [
                        r'title:\s*\{\s*[^}]*text:\s*["\']([^"\']+)["\']',
                        r'text:\s*["\']([^"\']+)["\'].*title',
                        r'charttitle:\s*([^,\}]+)',
                    ]
                    for pattern in chart_title_patterns:
                        title_match = re.search(pattern, after_canvas, re.IGNORECASE)
                        if title_match:
                            title = title_match.group(1).strip().strip('"\'')
                            break
            
            # Fallback to chart_id if no title found
            if not title:
                title = chart_id
            
            # Extract chart type and sample data from JavaScript
            chart_type = 'line'  # default
            sample_labels = []
            sample_datasets = []
            
            if canvas_pos > 0:
                # Look for Chart.js configuration after the canvas
                after_canvas = content[canvas_pos:canvas_pos + 5000]  # Look 5000 chars ahead
                
                # Find the Chart.js initialization for this canvas
                # Find Chart.js initialization for this canvas
                # Pattern 1: Look for getElementById with chart_id, then find the Chart initialization after it
                get_element_pattern = rf'getElementById\s*\(["\']?{re.escape(chart_id)}["\']?\)'
                get_element_match = re.search(get_element_pattern, after_canvas, re.IGNORECASE)
                
                chart_config = None
                if get_element_match:
                    # Get content after getElementById call (should contain Chart initialization)
                    chart_section_start = get_element_match.end()
                    chart_section = after_canvas[chart_section_start:chart_section_start + 2000]  # Look 2000 chars ahead
                    
                    # Find Chart initialization after getElementById
                    # Look for: new Chart(ctx, { type: '...', data: {...}, options: {...} })
                    chart_init_match = re.search(r'new\s+Chart\s*\([^)]*ctx[^)]*,\s*\{', chart_section, re.IGNORECASE | re.DOTALL)
                    if chart_init_match:
                        # Get the full Chart configuration (from new Chart to closing brace)
                        chart_start = chart_init_match.start()
                        # Find the matching closing brace for the Chart config object
                        brace_count = 0
                        chart_end = chart_start
                        in_string = False
                        string_char = None
                        for i, char in enumerate(chart_section[chart_start:], start=chart_start):
                            if char in ['"', "'"] and (i == chart_start or chart_section[i-1] != '\\'):
                                if not in_string:
                                    in_string = True
                                    string_char = char
                                elif char == string_char:
                                    in_string = False
                                    string_char = None
                            elif not in_string:
                                if char == '{':
                                    brace_count += 1
                                elif char == '}':
                                    brace_count -= 1
                                    if brace_count == 0:
                                        chart_end = i + 1
                                        break
                        if chart_end > chart_start:
                            chart_config = chart_section[chart_start:chart_end]
                
                if chart_config:
                    
                    # Extract type
                    type_pattern = r"type:\s*['\"]([^'\"]+)['\"]"
                    type_match = re.search(type_pattern, chart_config, re.IGNORECASE)
                    if type_match:
                        chart_type = type_match.group(1).lower()
                    
                    # Extract labels (try to find labels array)
                    labels_patterns = [
                        r"labels:\s*(\[[^\]]+\])",
                        r"labels:\s*(\{[^}]+\})",
                        r"labels:\s*([^,\}]+)",
                    ]
                    for pattern in labels_patterns:
                        labels_match = re.search(pattern, chart_config, re.IGNORECASE)
                        if labels_match:
                            try:
                                # Try to parse as JSON or extract values
                                labels_str = labels_match.group(1)
                                # If it's a Jinja template variable, try to get actual data from dashboard
                                if '|' in labels_str or '{{' in labels_str:
                                    # Extract variable name (e.g., {{ sex_labels|tojson }} -> sex_labels)
                                    var_match = re.search(r'\{\{\s*([^|}\s]+)', labels_str)
                                    if var_match and dashboard_data:
                                        var_name = var_match.group(1).strip()
                                        # Try to get actual data from dashboard_data
                                        # Pattern 1: Direct match (e.g., sex_labels in dashboard_data)
                                        if var_name in dashboard_data:
                                            actual_data = dashboard_data[var_name]
                                            if isinstance(actual_data, dict) and 'labels' in actual_data:
                                                sample_labels = actual_data['labels']
                                            elif isinstance(actual_data, list):
                                                sample_labels = actual_data
                                        # Pattern 2: sex_labels -> sex_data['labels'] (common pattern)
                                        # In dashboard_data, we have sex_data, not sex_labels
                                        elif var_name.endswith('_labels') and dashboard_data:
                                            base_name = var_name.replace('_labels', '')
                                            # Try sex_data, sexData, etc.
                                            for data_key in [f'{base_name}_data', f'{base_name}Data', f'{base_name}']:
                                                if data_key in dashboard_data and isinstance(dashboard_data[data_key], dict):
                                                    labels = dashboard_data[data_key].get('labels', [])
                                                    if labels:
                                                        sample_labels = labels
                                                        break
                                        # Pattern 3: Check if it's a direct key in dashboard_data
                                        elif var_name in dashboard_data:
                                            if isinstance(dashboard_data[var_name], list):
                                                sample_labels = dashboard_data[var_name]
                                        # Pattern 4: If var_name is like 'sex_labels', check for 'sex_data' in dashboard_data
                                        if not sample_labels and var_name.endswith('_labels'):
                                            base = var_name.replace('_labels', '')
                                            # Check for base_data (e.g., sex_data) in dashboard_data
                                            for key in dashboard_data.keys():
                                                if key.startswith(base) and isinstance(dashboard_data[key], dict):
                                                    labels = dashboard_data[key].get('labels', [])
                                                    if labels:
                                                        sample_labels = labels
                                                        break
                                    # Fallback to sample if no actual data found
                                    if not sample_labels:
                                        sample_labels = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد']
                                else:
                                    # Try to parse as JSON
                                    import json
                                    sample_labels = json.loads(labels_str)
                            except Exception as e:
                                logger.warning(f"Error extracting labels for {chart_id}: {e}")
                                sample_labels = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد']
                            break
                    
                    # Extract datasets (try to find data array)
                    data_patterns = [
                        r"data:\s*(\[[^\]]+\])",
                        r"data:\s*(\{[^}]+\})",
                    ]
                    for pattern in data_patterns:
                        data_match = re.search(pattern, chart_config, re.IGNORECASE)
                        if data_match:
                            try:
                                data_str = data_match.group(1)
                                # If it's a Jinja template variable, try to get actual data from dashboard
                                if '|' in data_str or '{{' in data_str:
                                    # Extract variable name (e.g., {{ sex_counts|tojson }} -> sex_counts)
                                    var_match = re.search(r'\{\{\s*([^|}\s]+)', data_str)
                                    if var_match and dashboard_data:
                                        var_name = var_match.group(1).strip()
                                        # Try to get actual data from dashboard_data
                                        # Pattern 1: Direct match (e.g., sex_counts in dashboard_data)
                                        if var_name in dashboard_data:
                                            actual_data = dashboard_data[var_name]
                                            if isinstance(actual_data, list):
                                                # Determine colors based on chart type
                                                if chart_type in ['pie', 'doughnut']:
                                                    colors = ['#36A2EB', '#FF6384', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40', '#C9CBCF']
                                                    sample_datasets = [{
                                                        'data': actual_data,
                                                        'backgroundColor': colors[:len(actual_data)]
                                                    }]
                                                else:
                                                    sample_datasets = [{
                                                        'data': actual_data,
                                                        'backgroundColor': 'rgba(54, 162, 235, 0.2)',
                                                        'borderColor': 'rgba(54, 162, 235, 1)'
                                                    }]
                                        # Pattern 2: sex_counts -> sex_data['counts'] (common pattern)
                                        # In dashboard_data, we have sex_data, not sex_counts
                                        elif var_name.endswith('_counts') and dashboard_data:
                                            base_name = var_name.replace('_counts', '')
                                            # Try sex_data, sexData, etc.
                                            for data_key in [f'{base_name}_data', f'{base_name}Data', f'{base_name}']:
                                                if data_key in dashboard_data and isinstance(dashboard_data[data_key], dict):
                                                    counts = dashboard_data[data_key].get('counts', [])
                                                    if counts:
                                                        if chart_type in ['pie', 'doughnut']:
                                                            colors = ['#36A2EB', '#FF6384', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40', '#C9CBCF']
                                                            sample_datasets = [{
                                                                'data': counts,
                                                                'backgroundColor': colors[:len(counts)]
                                                            }]
                                                        else:
                                                            sample_datasets = [{
                                                                'data': counts,
                                                                'backgroundColor': 'rgba(54, 162, 235, 0.2)',
                                                                'borderColor': 'rgba(54, 162, 235, 1)'
                                                            }]
                                                        break
                                        # Pattern 3: If var_name is like 'sex_counts', check for 'sex_data' in dashboard_data
                                        if not sample_datasets and var_name.endswith('_counts'):
                                            base = var_name.replace('_counts', '')
                                            # Check for base_data (e.g., sex_data) in dashboard_data
                                            for key in dashboard_data.keys():
                                                if key.startswith(base) and isinstance(dashboard_data[key], dict):
                                                    counts = dashboard_data[key].get('counts', [])
                                                    if counts:
                                                        if chart_type in ['pie', 'doughnut']:
                                                            colors = ['#36A2EB', '#FF6384', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40', '#C9CBCF']
                                                            sample_datasets = [{
                                                                'data': counts,
                                                                'backgroundColor': colors[:len(counts)]
                                                            }]
                                                        else:
                                                            sample_datasets = [{
                                                                'data': counts,
                                                                'backgroundColor': 'rgba(54, 162, 235, 0.2)',
                                                                'borderColor': 'rgba(54, 162, 235, 1)'
                                                            }]
                                                        break
                                    # Fallback to sample if no actual data found
                                    if not sample_datasets:
                                        if chart_type in ['pie', 'doughnut']:
                                            sample_datasets = [{'data': [330, 649], 'backgroundColor': ['#36A2EB', '#FF6384']}]
                                        else:
                                            sample_datasets = [{'data': [12, 19, 3, 5, 2], 'backgroundColor': 'rgba(54, 162, 235, 0.2)'}]
                                else:
                                    import json
                                    data = json.loads(data_str)
                                    if isinstance(data, list):
                                        sample_datasets = [{'data': data}]
                            except Exception as e:
                                logger.warning(f"Error extracting data for {chart_id}: {e}")
                                pass
                            break
            
            # If no sample data extracted, use defaults based on chart type
            if not sample_labels:
                if chart_type in ['pie', 'doughnut']:
                    sample_labels = ['مرد', 'زن']
                else:
                    sample_labels = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد']
            if not sample_datasets:
                if chart_type in ['pie', 'doughnut']:
                    sample_datasets = [{'data': [330, 649], 'backgroundColor': ['#36A2EB', '#FF6384', '#FFCE56', '#4BC0C0', '#9966FF']}]
                elif chart_type == 'bar':
                    sample_datasets = [{'data': [12, 19, 3, 5, 2], 'backgroundColor': 'rgba(255, 159, 64, 0.6)', 'borderColor': 'rgba(255, 159, 64, 1)'}]
                else:
                    sample_datasets = [{'data': [12, 19, 3, 5, 2], 'backgroundColor': 'rgba(54, 162, 235, 0.2)', 'borderColor': 'rgba(54, 162, 235, 1)'}]
            
            # Get existing config from database
            try:
                config = ChartConfig.query.filter_by(
                    template_name=template_name,
                    chart_id=chart_id
                ).first()
            except Exception as db_error:
                logger.warning(f"Error querying ChartConfig (table may not exist): {db_error}")
                config = None
            
            if config:
                config_dict = config.to_dict()
                # Use saved title from database - only use extracted HTML title if DB title is missing or same as chart_id
                if not config_dict.get('title') or config_dict.get('title') == chart_id:
                    config_dict['title'] = title
                # Use saved chart_type from database - only update if DB type is default (line) and we found a different type
                if config_dict.get('chart_type') == 'line' and chart_type != 'line':
                    config_dict['chart_type'] = chart_type
                # Ensure display_order is present
                if config_dict.get('display_order') is None:
                    config_dict['display_order'] = len(charts)
                # Add sample data if not present
                if not config_dict.get('chart_options') or 'sample_labels' not in config_dict.get('chart_options', {}):
                    if not config_dict.get('chart_options'):
                        config_dict['chart_options'] = {}
                    config_dict['chart_options']['sample_labels'] = sample_labels
                    config_dict['chart_options']['sample_datasets'] = sample_datasets
                charts.append(config_dict)
            else:
                # Create default config - use extracted type if found
                charts.append({
                    'id': None,
                    'template_name': template_name,
                    'chart_id': chart_id,
                    'title': title,
                    'display_order': len(charts),
                    'chart_type': chart_type,  # Use extracted type instead of default 'line'
                    'show_labels': True,
                    'show_legend': True,
                    'allow_export': True,
                    'chart_options': {
                        'sample_labels': sample_labels,
                        'sample_datasets': sample_datasets
                    }
                })
        
        # Sort by display_order
        charts.sort(key=lambda x: x.get('display_order', 0))
        
        return jsonify({
            'success': True,
            'charts': charts
        })
    except Exception as e:
        logger.error(f"Error getting chart configs for {template_name}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'خطا در دریافت تنظیمات نمودارها: {str(e)}'
        }), 500


@admin_bp.route('/dashboards/templates/<template_name>/charts', methods=['POST'])
@login_required
@admin_required
def dashboard_template_charts_save(template_name):
    """Save chart configurations for a template"""
    try:
        log_action('save_chart_configs', 'template', template_name)
    except Exception as e:
        logger.warning(f"Error logging action: {e}")
    
    try:
        # Security check
        if not template_name.endswith('.html') or '..' in template_name or '/' in template_name:
            return jsonify({'success': False, 'message': 'نام فایل نامعتبر است'}), 400
        
        # Get template path
        base_dir = Path(__file__).parent.parent
        template_path = base_dir / 'templates' / 'dashboards' / template_name
        
        if not template_path.exists():
            return jsonify({'success': False, 'message': 'تمپلیت یافت نشد'}), 404
        
        # Create backup before making changes
        next_version = None
        try:
            # Read current template content
            with open(template_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
            
            # Get current chart configs
            current_chart_configs = []
            try:
                configs = ChartConfig.query.filter_by(template_name=template_name).all()
                current_chart_configs = [config.to_dict() for config in configs]
            except Exception as e:
                logger.warning(f"Error getting current chart configs: {e}")
            
            # Get next version number
            try:
                max_version = db.session.query(func.max(TemplateVersion.version_number)).filter_by(
                    template_name=template_name
                ).scalar() or 0
                next_version = max_version + 1
            except Exception as e:
                logger.warning(f"Error getting max version number: {e}")
                next_version = 1
            
            # Keep only last 50 versions
            if next_version and next_version > 50:
                try:
                    # Delete oldest versions
                    versions_to_delete = TemplateVersion.query.filter_by(
                        template_name=template_name
                    ).order_by(TemplateVersion.version_number.asc()).limit(next_version - 50).all()
                    for version in versions_to_delete:
                        db.session.delete(version)
                except Exception as e:
                    logger.warning(f"Error deleting old versions: {e}")
            
            # Create version backup
            if next_version:
                try:
                    version = TemplateVersion(
                        template_name=template_name,
                        version_number=next_version,
                        template_content=current_content,
                        chart_configs=current_chart_configs,
                        created_by=current_user.id,
                        description=f'ذخیره خودکار قبل از اعمال تغییرات - نسخه {next_version}'
                    )
                    db.session.add(version)
                    db.session.flush()  # Flush to get version ID
                    
                    logger.info(f"Created template version {next_version} for {template_name}")
                except Exception as e:
                    logger.error(f"Error creating version record: {e}", exc_info=True)
                    next_version = None  # Reset if creation failed
        except Exception as backup_error:
            logger.error(f"Error creating template backup: {backup_error}", exc_info=True)
            # Continue even if backup fails, but log the error
            # Don't fail the save operation if backup fails
            next_version = None
        
        # Get data from request
        if not request.is_json:
            return jsonify({'success': False, 'message': 'درخواست باید JSON باشد'}), 400
        
        data = request.get_json()
        charts = data.get('charts', [])
        
        # Log received data for debugging
        logger.info(f"Received chart data for {template_name}: {len(charts)} charts")
        for idx, chart_data in enumerate(charts):
            logger.info(f"Chart {idx}: id={chart_data.get('chart_id')}, title={chart_data.get('title')}, order={chart_data.get('display_order')}, type={chart_data.get('chart_type')}")
        
        if not charts:
            return jsonify({'success': False, 'message': 'هیچ نموداری ارسال نشده است'}), 400
        
        saved_charts = []
        for chart_data in charts:
            chart_id = chart_data.get('chart_id')
            if not chart_id:
                continue
            
            # Find or create config
            try:
                config = ChartConfig.query.filter_by(
                    template_name=template_name,
                    chart_id=chart_id
                ).first()
            except Exception as db_error:
                logger.warning(f"Error querying ChartConfig: {db_error}")
                config = None
            
            if not config:
                config = ChartConfig(
                    template_name=template_name,
                    chart_id=chart_id,
                    created_by=current_user.id
                )
                db.session.add(config)
            
            # Update config - ensure all fields are saved
            # Get values from request data, fallback to existing config, then to defaults
            new_title = chart_data.get('title')
            if new_title is not None and new_title != '':
                config.title = new_title
            elif not config.title:
                config.title = chart_id
            
            new_display_order = chart_data.get('display_order')
            if new_display_order is not None:
                config.display_order = int(new_display_order)
            elif config.display_order is None:
                config.display_order = 0
            
            new_chart_type = chart_data.get('chart_type')
            if new_chart_type:
                config.chart_type = new_chart_type
            elif not config.chart_type:
                config.chart_type = 'line'
            
            new_show_labels = chart_data.get('show_labels')
            if new_show_labels is not None:
                config.show_labels = bool(new_show_labels)
            elif config.show_labels is None:
                config.show_labels = True
            
            new_show_legend = chart_data.get('show_legend')
            if new_show_legend is not None:
                config.show_legend = bool(new_show_legend)
            elif config.show_legend is None:
                config.show_legend = True
            
            new_allow_export = chart_data.get('allow_export')
            if new_allow_export is not None:
                config.allow_export = bool(new_allow_export)
            elif config.allow_export is None:
                config.allow_export = True
            
            new_chart_options = chart_data.get('chart_options')
            if new_chart_options is not None:
                config.chart_options = new_chart_options
            elif config.chart_options is None:
                config.chart_options = {}
            
            config.updated_at = datetime.utcnow()
            
            # Log for debugging
            logger.info(f"Saving chart config: {chart_id}, title: '{config.title}', order: {config.display_order}, type: {config.chart_type}, labels: {config.show_labels}, legend: {config.show_legend}, export: {config.allow_export}")
            
            saved_charts.append(config.to_dict())
        
        try:
            db.session.commit()
        except Exception as commit_error:
            db.session.rollback()
            logger.error(f"Error committing chart configs: {commit_error}", exc_info=True)
            raise
        
        # Log saved data for verification
        logger.info(f"Chart configs for {template_name} updated by user {current_user.id}")
        for saved_chart in saved_charts:
            logger.info(f"Saved chart: id={saved_chart.get('chart_id')}, title='{saved_chart.get('title')}', order={saved_chart.get('display_order')}, type={saved_chart.get('chart_type')}, labels={saved_chart.get('show_labels')}, legend={saved_chart.get('show_legend')}, export={saved_chart.get('allow_export')}")
        
        # Apply chart configurations to HTML file
        html_updated = False
        try:
            html_updated = apply_chart_configs_to_html(template_path, saved_charts)
            if html_updated:
                logger.info(f"HTML template {template_name} updated with chart configurations")
            else:
                logger.warning(f"Could not update HTML template {template_name} with chart configurations")
        except Exception as html_error:
            logger.error(f"Error updating HTML template: {html_error}", exc_info=True)
            # Continue even if HTML update fails - database save was successful
        
        # Prepare success message
        if next_version:
            if html_updated:
                message = f'{len(saved_charts)} تنظیمات نمودار ذخیره شد و فایل HTML به‌روزرسانی شد. نسخه پشتیبان {next_version} ایجاد شد.'
            else:
                message = f'{len(saved_charts)} تنظیمات نمودار در دیتابیس ذخیره شد. (خطا در به‌روزرسانی فایل HTML) نسخه پشتیبان {next_version} ایجاد شد.'
        else:
            if html_updated:
                message = f'{len(saved_charts)} تنظیمات نمودار ذخیره شد و فایل HTML به‌روزرسانی شد.'
            else:
                message = f'{len(saved_charts)} تنظیمات نمودار در دیتابیس ذخیره شد. (خطا در به‌روزرسانی فایل HTML یا ایجاد نسخه پشتیبان)'
        
        return jsonify({
            'success': True,
            'message': message,
            'charts': saved_charts,
            'version_number': next_version,
            'html_updated': html_updated
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error saving chart configs for {template_name}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'خطا در ذخیره تنظیمات: {str(e)}'
        }), 500


@admin_bp.route('/dashboards/templates/<template_name>/versions', methods=['GET'])
@login_required
@admin_required
def dashboard_template_versions(template_name):
    """Get version history for a template"""
    try:
        # Security check
        if not template_name.endswith('.html') or '..' in template_name or '/' in template_name:
            return jsonify({'success': False, 'message': 'نام فایل نامعتبر است'}), 400
        
        # Get versions (newest first)
        versions = TemplateVersion.query.filter_by(
            template_name=template_name
        ).order_by(TemplateVersion.version_number.desc()).limit(50).all()
        
        return jsonify({
            'success': True,
            'versions': [v.to_dict() for v in versions]
        })
    except Exception as e:
        logger.error(f"Error getting template versions for {template_name}: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'خطا در دریافت نسخه‌ها: {str(e)}'
        }), 500


@admin_bp.route('/dashboards/templates/<template_name>/versions/<int:version_number>/restore', methods=['POST'])
@login_required
@admin_required
def dashboard_template_restore_version(template_name, version_number):
    """Restore a template to a previous version"""
    try:
        # Security check
        if not template_name.endswith('.html') or '..' in template_name or '/' in template_name:
            return jsonify({'success': False, 'message': 'نام فایل نامعتبر است'}), 400
        
        # Get version
        version = TemplateVersion.query.filter_by(
            template_name=template_name,
            version_number=version_number
        ).first()
        
        if not version:
            return jsonify({'success': False, 'message': 'نسخه یافت نشد'}), 404
        
        # Get template path
        base_dir = Path(__file__).parent.parent
        template_path = base_dir / 'templates' / 'dashboards' / template_name
        
        if not template_path.exists():
            return jsonify({'success': False, 'message': 'تمپلیت یافت نشد'}), 404
        
        # Restore template content (no backup created before restore)
        try:
            with open(template_path, 'w', encoding='utf-8') as f:
                f.write(version.template_content)
        except Exception as e:
            logger.error(f"Error restoring template content: {e}", exc_info=True)
            return jsonify({'success': False, 'message': f'خطا در بازگردانی محتوای تمپلیت: {str(e)}'}), 500
        
        # Restore chart configs if available
        if version.chart_configs:
            try:
                # Delete existing configs
                ChartConfig.query.filter_by(template_name=template_name).delete()
                
                # Restore configs - ensure all fields are restored
                for config_data in version.chart_configs:
                    config = ChartConfig(
                        template_name=config_data.get('template_name', template_name),
                        chart_id=config_data.get('chart_id'),
                        title=config_data.get('title') or config_data.get('chart_id', ''),
                        display_order=int(config_data.get('display_order', 0)),
                        chart_type=config_data.get('chart_type', 'line'),
                        show_labels=bool(config_data.get('show_labels', True)),
                        show_legend=bool(config_data.get('show_legend', True)),
                        allow_export=bool(config_data.get('allow_export', True)),
                        chart_options=config_data.get('chart_options', {}),
                        created_by=current_user.id
                    )
                    db.session.add(config)
                    logger.debug(f"Restoring chart config: {config.chart_id}, title: {config.title}, order: {config.display_order}, type: {config.chart_type}")
            except Exception as e:
                logger.warning(f"Error restoring chart configs: {e}", exc_info=True)
                # Continue even if chart config restore fails
        
        db.session.commit()
        
        log_action('restore_template_version', 'template', template_name, {'version': version_number})
        
        logger.info(f"Template {template_name} restored to version {version_number} by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': f'تمپلیت به نسخه {version_number} بازگردانده شد'
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error restoring template version: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'خطا در بازگردانی نسخه: {str(e)}'
        }), 500


@admin_bp.route('/dashboards/templates/<template_name>/versions/<int:version_number>/delete', methods=['POST'])
@login_required
@admin_required
def dashboard_template_delete_version(template_name, version_number):
    """Delete a template version"""
    try:
        # Security check
        if not template_name.endswith('.html') or '..' in template_name or '/' in template_name:
            return jsonify({'success': False, 'message': 'نام فایل نامعتبر است'}), 400
        
        # Get version
        version = TemplateVersion.query.filter_by(
            template_name=template_name,
            version_number=version_number
        ).first()
        
        if not version:
            return jsonify({'success': False, 'message': 'نسخه یافت نشد'}), 404
        
        # Delete version
        db.session.delete(version)
        db.session.commit()
        
        log_action('delete_template_version', 'template', template_name, {'version': version_number})
        
        logger.info(f"Template version {version_number} for {template_name} deleted by user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': f'نسخه {version_number} با موفقیت حذف شد'
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting template version: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'خطا در حذف نسخه: {str(e)}'
        }), 500
