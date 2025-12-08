"""
Admin Panel Models
Additional models for admin panel functionality
"""
from extensions import db
from datetime import datetime
from jdatetime import datetime as jdatetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, Float
from sqlalchemy.orm import relationship
from typing import Optional, Dict, Any


class DashboardAccess(db.Model):
    """User access permissions for specific dashboards"""
    __tablename__ = 'dashboard_access'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    dashboard_id = Column(String(100), nullable=False)  # e.g., 'd1', 'd2', 'students'
    
    # Access restrictions
    can_access = Column(Boolean, default=True, nullable=False)
    
    # Filter restrictions (JSON format)
    # Example: {"province_codes": [1, 2], "university_codes": [10], "faculty_codes": [100]}
    filter_restrictions = Column(JSON, nullable=True)
    
    # Date range restrictions
    date_from = Column(DateTime, nullable=True)
    date_to = Column(DateTime, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    
    # Relationships
    user = relationship('User', foreign_keys=[user_id], backref='dashboard_accesses')
    creator = relationship('User', foreign_keys=[created_by])
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'dashboard_id': self.dashboard_id,
            'can_access': self.can_access,
            'filter_restrictions': self.filter_restrictions or {},
            'date_from': self.date_from.isoformat() if self.date_from else None,
            'date_to': self.date_to.isoformat() if self.date_to else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class AccessLog(db.Model):
    """Log of user actions for audit trail"""
    __tablename__ = 'access_logs'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    action = Column(String(100), nullable=False)  # e.g., 'view_dashboard', 'export_data', 'modify_user'
    resource_type = Column(String(50), nullable=True)  # e.g., 'dashboard', 'user', 'data'
    resource_id = Column(String(100), nullable=True)  # e.g., 'd1', user_id, etc.
    
    # Request details
    ip_address = Column(String(45), nullable=True)  # IPv6 compatible
    user_agent = Column(Text, nullable=True)
    request_path = Column(String(500), nullable=True)
    request_method = Column(String(10), nullable=True)
    
    # Additional context
    details = Column(JSON, nullable=True)  # Additional context as JSON
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship('User', backref='access_logs')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_name': self.user.name if self.user else None,
            'action': self.action,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id,
            'ip_address': self.ip_address,
            'request_path': self.request_path,
            'details': self.details or {},
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'created_at_jalali': self.get_jalali_date() if self.created_at else None,
        }
    
    def get_jalali_date(self) -> str:
        """Get Jalali date string"""
        if not self.created_at:
            return None
        jd = jdatetime.fromgregorian(datetime=self.created_at)
        return jd.strftime('%Y/%m/%d %H:%M:%S')


class DataSync(db.Model):
    """Track data synchronization from API Gateway"""
    __tablename__ = 'data_syncs'
    
    id = Column(Integer, primary_key=True)
    data_source = Column(String(100), nullable=False, unique=True)  # e.g., 'faculty', 'students', 'lms'
    sync_type = Column(String(50), nullable=False)  # 'auto', 'manual', 'scheduled'
    
    # Sync status
    status = Column(String(50), nullable=False, default='pending')  # 'pending', 'running', 'success', 'failed'
    last_sync_at = Column(DateTime, nullable=True)
    next_sync_at = Column(DateTime, nullable=True)
    
    # Sync configuration
    auto_sync_enabled = Column(Boolean, default=True, nullable=False)
    sync_interval_value = Column(Integer, default=60, nullable=False)  # Interval value (e.g., 60)
    sync_interval_unit = Column(String(20), default='minutes', nullable=False)  # 'minutes', 'hours', 'days'
    
    # API Gateway details
    api_base_url = Column(String(500), nullable=True)  # Base URL for API (e.g., https://api.cfu.ac.ir)
    api_endpoint = Column(String(500), nullable=True)  # Full endpoint URL
    api_method = Column(String(10), default='GET', nullable=False)
    api_username = Column(String(200), nullable=True)  # API authentication username
    api_password = Column(String(500), nullable=True)  # API authentication password (should be encrypted in production)
    api_params = Column(JSON, nullable=True)
    
    # Sync results
    records_synced = Column(Integer, default=0, nullable=False)
    sync_duration_seconds = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_synced_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    
    # Relationships
    syncer = relationship('User', foreign_keys=[last_synced_by])
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'data_source': self.data_source,
            'sync_type': self.sync_type,
            'status': self.status,
            'last_sync_at': self.last_sync_at.isoformat() if self.last_sync_at else None,
            'last_sync_at_jalali': self.get_jalali_date(self.last_sync_at) if self.last_sync_at else None,
            'next_sync_at': self.next_sync_at.isoformat() if self.next_sync_at else None,
            'next_sync_at_jalali': self.get_jalali_date(self.next_sync_at) if self.next_sync_at else None,
            'auto_sync_enabled': self.auto_sync_enabled,
            'sync_interval_value': self.sync_interval_value,
            'sync_interval_unit': self.sync_interval_unit,
            'api_endpoint': self.api_endpoint,
            'records_synced': self.records_synced,
            'sync_duration_seconds': self.sync_duration_seconds,
            'error_message': self.error_message,
        }
    
    @staticmethod
    def get_jalali_date(dt: Optional[datetime]) -> Optional[str]:
        """Get Jalali date string"""
        try:
            if not dt:
                return None
            if isinstance(dt, str):
                # If it's a string, try to parse it
                try:
                    dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
                except:
                    return str(dt)
            jd = jdatetime.fromgregorian(datetime=dt)
            return jd.strftime('%Y/%m/%d %H:%M:%S')
        except Exception as e:
            # Fallback to string representation
            return str(dt) if dt else None
    
    def get_interval_minutes(self) -> int:
        """Convert interval to minutes"""
        try:
            sync_interval_unit = getattr(self, 'sync_interval_unit', None)
            sync_interval_value = getattr(self, 'sync_interval_value', None)
            
            if not sync_interval_unit:
                # Fallback for old records
                sync_interval_minutes = getattr(self, 'sync_interval_minutes', None)
                if sync_interval_minutes:
                    return sync_interval_minutes
                return 60
            
            if not sync_interval_value:
                return 60
            
            if sync_interval_unit == 'minutes':
                return sync_interval_value
            elif sync_interval_unit == 'hours':
                return sync_interval_value * 60
            elif sync_interval_unit == 'days':
                return sync_interval_value * 24 * 60
            return sync_interval_value
        except (AttributeError, KeyError):
            # Fallback if columns don't exist
            return 60
    
    def get_interval_display(self) -> str:
        """Get human-readable interval display"""
        try:
            sync_interval_unit = getattr(self, 'sync_interval_unit', None)
            sync_interval_value = getattr(self, 'sync_interval_value', None)
            
            # Fallback for old records
            if not sync_interval_unit:
                sync_interval_minutes = getattr(self, 'sync_interval_minutes', None)
                if sync_interval_minutes:
                    return f"{sync_interval_minutes} دقیقه"
                return "60 دقیقه"
            
            if not sync_interval_value:
                return "60 دقیقه"
            
            unit_names = {
                'minutes': 'دقیقه',
                'hours': 'ساعت',
                'days': 'روز'
            }
            unit_name = unit_names.get(sync_interval_unit, sync_interval_unit)
            return f"{sync_interval_value} {unit_name}"
        except (AttributeError, KeyError, Exception) as e:
            # Fallback if columns don't exist or any error occurs
            return "60 دقیقه"


class DashboardConfig(db.Model):
    """Configuration for dashboards"""
    __tablename__ = 'dashboard_configs'
    
    id = Column(Integer, primary_key=True)
    dashboard_id = Column(String(100), unique=True, nullable=False)
    
    # Display settings
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(100), nullable=True)  # Icon class or URL
    order = Column(Integer, default=0, nullable=False)  # Display order
    
    # Access settings
    is_active = Column(Boolean, default=True, nullable=False)
    is_public = Column(Boolean, default=False, nullable=False)  # Public dashboards visible to all
    
    # Data settings
    cache_ttl_seconds = Column(Integer, default=300, nullable=False)  # Cache TTL
    refresh_interval_seconds = Column(Integer, nullable=True)  # Auto-refresh interval
    
    # Custom configuration (JSON)
    config = Column(JSON, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    
    # Relationships
    creator = relationship('User', foreign_keys=[created_by])
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'dashboard_id': self.dashboard_id,
            'title': self.title,
            'description': self.description,
            'icon': self.icon,
            'order': self.order,
            'is_active': self.is_active,
            'is_public': self.is_public,
            'cache_ttl_seconds': self.cache_ttl_seconds,
            'refresh_interval_seconds': self.refresh_interval_seconds,
            'config': self.config or {},
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class ChartConfig(db.Model):
    """Configuration for charts in dashboard templates"""
    __tablename__ = 'chart_configs'
    
    id = Column(Integer, primary_key=True)
    template_name = Column(String(200), nullable=False)  # e.g., 'd8.html'
    chart_id = Column(String(200), nullable=False)  # e.g., 'chart_1', 'ratioChart'
    
    # Chart display settings
    title = Column(String(500), nullable=True)  # Chart title
    display_order = Column(Integer, default=0, nullable=False)  # Order in dashboard
    
    # Chart type
    chart_type = Column(String(50), default='line', nullable=False)  # 'line', 'bar', 'pie', etc.
    
    # Display options
    is_visible = Column(Boolean, default=True, nullable=False)  # Show/hide chart
    show_labels = Column(Boolean, default=True, nullable=False)  # Show data labels
    show_legend = Column(Boolean, default=True, nullable=False)  # Show legend
    allow_export = Column(Boolean, default=True, nullable=False)  # Allow image export
    color_palette = Column(String(50), default='default', nullable=False)  # Color palette name
    
    # Chart options (JSON for additional settings)
    chart_options = Column(JSON, nullable=True)  # Additional Chart.js options
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    
    # Relationships
    creator = relationship('User', foreign_keys=[created_by])
    
    # Unique constraint: one config per chart in a template
    __table_args__ = (
        db.UniqueConstraint('template_name', 'chart_id', name='_template_chart_uc'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'template_name': self.template_name,
            'chart_id': self.chart_id,
            'title': self.title,
            'display_order': self.display_order,
            'chart_type': self.chart_type,
            'is_visible': self.is_visible,
            'show_labels': self.show_labels,
            'show_legend': self.show_legend,
            'allow_export': self.allow_export,
            'color_palette': self.color_palette,
            'chart_options': self.chart_options or {},
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class TemplateVersion(db.Model):
    """Version history for dashboard templates"""
    __tablename__ = 'template_versions'
    
    id = Column(Integer, primary_key=True)
    template_name = Column(String(200), nullable=False)  # e.g., 'd1.html'
    version_number = Column(Integer, nullable=False)  # Version number (1, 2, 3, ...)
    
    # Template content backup
    template_content = Column(Text, nullable=False)  # Full HTML content
    
    # Chart configurations backup (JSON)
    chart_configs = Column(JSON, nullable=True)  # All chart configs at this version
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    description = Column(Text, nullable=True)  # Optional description
    
    # Relationships
    creator = relationship('User', foreign_keys=[created_by])
    
    # Unique constraint: one version per template per version number
    __table_args__ = (
        db.UniqueConstraint('template_name', 'version_number', name='_template_version_uc'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        # Convert datetime to Jalali
        jdate = jdatetime.fromgregorian(datetime=self.created_at) if self.created_at else None
        return {
            'id': self.id,
            'template_name': self.template_name,
            'version_number': self.version_number,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'created_at_jalali': jdate.strftime('%Y/%m/%d %H:%M:%S') if jdate else None,
            'created_by': self.created_by,
            'description': self.description,
            'content_length': len(self.template_content) if self.template_content else 0,
        }

