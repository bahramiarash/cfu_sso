"""
Base Dashboard Class
All dashboards should inherit from this class
"""
from abc import ABC, abstractmethod
from flask import render_template, make_response, request
from functools import wraps
import logging
from typing import Dict, Any, Optional
from .context import UserContext, get_user_context
from .cache import DashboardCache, cached

logger = logging.getLogger(__name__)


class DashboardError(Exception):
    """Custom exception for dashboard errors"""
    pass


class BaseDashboard(ABC):
    """Base class for all dashboards"""
    
    def __init__(self, dashboard_id: str, title: str, description: Optional[str] = None):
        self.dashboard_id = dashboard_id
        self.title = title
        self.description = description
        self.logger = logging.getLogger(f"dashboard.{dashboard_id}")
        self.cache_enabled = True
        self.cache_ttl = 300  # 5 minutes default
    
    @abstractmethod
    def get_data(self, context: UserContext, **kwargs) -> Dict[str, Any]:
        """
        Fetch and process data for dashboard
        
        Args:
            context: UserContext object containing user's access level and filters
            **kwargs: Additional parameters from request (e.g., filters)
        
        Returns:
            Dictionary of data to be passed to template
        """
        pass
    
    @abstractmethod
    def render(self, data: Dict[str, Any], context: UserContext) -> Any:
        """
        Render dashboard template with data
        
        Args:
            data: Data dictionary from get_data()
            context: UserContext for template rendering
        
        Returns:
            Flask response object
        """
        pass
    
    def handle_request(self, user_context: Optional[UserContext] = None, **kwargs):
        """
        Main request handler with error handling and caching
        
        Args:
            user_context: UserContext object (will be fetched if not provided)
            **kwargs: Request parameters (filters, etc.)
        """
        try:
            # Get user context if not provided
            if user_context is None:
                user_context = get_user_context()
            
            # Check access permissions
            if not self.check_access(user_context):
                return self.render_error("شما دسترسی به این داشبورد را ندارید", 403)
            
            # Get filters from request
            filters = self._extract_filters_from_request(kwargs)
            
            # Apply user context filters
            filters = user_context.apply_filters(filters)
            
            # Generate cache key
            cache_key = self._generate_cache_key(user_context, filters)
            
            # Try to get from cache
            if self.cache_enabled:
                cached_data = DashboardCache.get(cache_key)
                if cached_data is not None:
                    self.logger.debug(f"Cache hit for {self.dashboard_id}")
                    return self.render(cached_data, user_context)
            
            # Fetch data
            data = self.get_data(user_context, **filters)
            
            # Cache the data
            if self.cache_enabled:
                DashboardCache.set(cache_key, data, self.cache_ttl)
            
            # Render
            return self.render(data, user_context)
            
        except ValueError as e:
            # Authentication/authorization error
            self.logger.warning(f"Access denied for {self.dashboard_id}: {e}")
            return self.render_error("شما دسترسی به این داشبورد را ندارید", 403)
        except Exception as e:
            self.logger.error(f"Error in dashboard {self.dashboard_id}: {e}", exc_info=True)
            return self.render_error(f"خطا در نمایش داشبورد: {str(e)}", 500)
    
    def check_access(self, context: UserContext) -> bool:
        """
        Check if user has access to this dashboard
        Override in subclasses for custom access control
        
        Args:
            context: UserContext object
        
        Returns:
            True if user has access, False otherwise
        """
        # Admin users have access to all dashboards
        if context.access_level.value == 'admin':
            return True
        
        # Check dashboard_access table for non-admin users
        from admin_models import DashboardAccess
        from extensions import db
        
        # Check if there's a specific access record
        access_record = DashboardAccess.query.filter_by(
            user_id=context.user.id,
            dashboard_id=self.dashboard_id
        ).first()
        
        if access_record:
            # If record exists, use its can_access value
            return access_record.can_access
        
        # If no record exists, check if dashboard is public
        from admin_models import DashboardConfig
        config = DashboardConfig.query.filter_by(dashboard_id=self.dashboard_id).first()
        if config and config.is_public:
            return True
        
        # Default: no access if not admin and no explicit access record
        return False
    
    def _extract_filters_from_request(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract filter parameters from request
        Override in subclasses for custom filter extraction
        
        Args:
            kwargs: Request parameters
        
        Returns:
            Dictionary of filters
        """
        filters = {}
        
        # Common filters
        if 'province_code' in kwargs:
            filters['province_code'] = int(kwargs['province_code'])
        
        if 'university_code' in kwargs:
            filters['university_code'] = int(kwargs['university_code'])
        
        if 'faculty_code' in kwargs:
            filters['faculty_code'] = int(kwargs['faculty_code'])
        
        if 'date_from' in kwargs:
            filters['date_from'] = kwargs['date_from']
        
        if 'date_to' in kwargs:
            filters['date_to'] = kwargs['date_to']
        
        return filters
    
    def _generate_cache_key(self, context: UserContext, filters: Dict[str, Any]) -> str:
        """Generate cache key for this dashboard"""
        key_data = {
            'dashboard_id': self.dashboard_id,
            'access_level': context.access_level.value,
            'province_code': context.province_code,
            'faculty_code': context.faculty_code,
            'filters': filters
        }
        return DashboardCache.generate_key(f"dashboard:{self.dashboard_id}", **key_data)
    
    def render_error(self, error_message: str, status_code: int = 500):
        """Render error page"""
        response = make_response(
            render_template("error.html", error=error_message),
            status_code
        )
        return self.add_no_cache_headers(response)
    
    def add_no_cache_headers(self, response):
        """Add no-cache headers to response"""
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    
    def get_template_context(self, data: Dict[str, Any], context: UserContext, **kwargs) -> Dict[str, Any]:
        """
        Prepare context for template rendering
        Adds user context and common data to template context
        
        Args:
            data: Dashboard data
            context: User context
            **kwargs: Additional context (filters, etc.)
        
        Returns:
            Complete template context
        """
        template_context = data.copy()
        template_context.update({
            'user_context': context.to_dict(),
            'dashboard_id': self.dashboard_id,
            'dashboard_title': self.title,
            'dashboard_description': self.description,
            'title': self.title,  # For backward compatibility
            'description': self.description,  # For backward compatibility
            'current_filters': kwargs.get('filters', {})
        })
        return template_context

