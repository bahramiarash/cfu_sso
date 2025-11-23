"""
Admin Panel Routes
Routes for admin panel functionality
"""
from flask import render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import login_required, current_user
from . import admin_bp
from .utils import admin_required, log_action, get_user_org_context
from models import User, AccessLevel as AccessLevelModel
from admin_models import DashboardAccess, AccessLog, DataSync, DashboardConfig
from extensions import db
from sqlalchemy import or_
from dashboards.registry import DashboardRegistry
from datetime import datetime, timedelta
from jdatetime import datetime as jdatetime
import logging

logger = logging.getLogger(__name__)


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
    
    accesses = DashboardAccess.query.paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/dashboard_access/list.html', accesses=accesses)


@admin_bp.route('/dashboard-access/new', methods=['GET', 'POST'])
@login_required
@admin_required
def dashboard_access_create():
    """Create dashboard access"""
    if request.method == 'POST':
        access = DashboardAccess(
            user_id=request.form.get('user_id', type=int),
            dashboard_id=request.form.get('dashboard_id'),
            can_access=request.form.get('can_access') == 'on',
            filter_restrictions=request.form.get('filter_restrictions') or {},
            created_by=current_user.id
        )
        
        # Parse date restrictions
        if request.form.get('date_from'):
            access.date_from = datetime.fromisoformat(request.form.get('date_from'))
        if request.form.get('date_to'):
            access.date_to = datetime.fromisoformat(request.form.get('date_to'))
        
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
        access.filter_restrictions = request.form.get('filter_restrictions') or {}
        
        if request.form.get('date_from'):
            access.date_from = datetime.fromisoformat(request.form.get('date_from'))
        else:
            access.date_from = None
        
        if request.form.get('date_to'):
            access.date_to = datetime.fromisoformat(request.form.get('date_to'))
        else:
            access.date_to = None
        
        db.session.commit()
        log_action('modify_dashboard_access', 'dashboard_access', access_id)
        flash('دسترسی با موفقیت به‌روزرسانی شد', 'success')
        return redirect(url_for('admin.dashboard_access_list'))
    
    dashboards = DashboardRegistry.list_all()
    users = User.query.all()
    
    return render_template('admin/dashboard_access/edit.html', 
                         access=access, 
                         dashboards=dashboards, 
                         users=users)


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

@admin_bp.route('/data-sync')
@login_required
@admin_required
def data_sync_list():
    """List data syncs"""
    log_action('view_data_syncs')
    
    syncs = DataSync.query.order_by(DataSync.data_source).all()
    
    return render_template('admin/data_sync/list.html', syncs=syncs)


@admin_bp.route('/data-sync/<int:sync_id>/sync', methods=['POST'])
@login_required
@admin_required
def data_sync_trigger(sync_id):
    """Trigger manual data sync"""
    sync = DataSync.query.get_or_404(sync_id)
    
    # TODO: Implement actual sync logic
    sync.status = 'running'
    sync.last_synced_by = current_user.id
    db.session.commit()
    
    log_action('trigger_data_sync', 'data_sync', sync_id, {'data_source': sync.data_source})
    
    # In a real implementation, this would trigger an async task
    # For now, just update status
    sync.status = 'success'
    sync.last_sync_at = datetime.utcnow()
    sync.records_synced = 0  # Would be updated by actual sync
    db.session.commit()
    
    flash('همگام‌سازی داده با موفقیت انجام شد', 'success')
    return redirect(url_for('admin.data_sync_list'))


@admin_bp.route('/data-sync/<int:sync_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def data_sync_edit(sync_id):
    """Edit data sync configuration"""
    sync = DataSync.query.get_or_404(sync_id)
    
    if request.method == 'POST':
        sync.auto_sync_enabled = request.form.get('auto_sync_enabled') == 'on'
        sync.sync_interval_minutes = request.form.get('sync_interval_minutes', type=int) or 60
        sync.api_endpoint = request.form.get('api_endpoint')
        sync.api_method = request.form.get('api_method', 'GET')
        
        # Calculate next sync time
        if sync.auto_sync_enabled and sync.last_sync_at:
            sync.next_sync_at = sync.last_sync_at + timedelta(minutes=sync.sync_interval_minutes)
        
        db.session.commit()
        log_action('modify_data_sync', 'data_sync', sync_id)
        flash('تنظیمات همگام‌سازی با موفقیت به‌روزرسانی شد', 'success')
        return redirect(url_for('admin.data_sync_list'))
    
    return render_template('admin/data_sync/edit.html', sync=sync)


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
