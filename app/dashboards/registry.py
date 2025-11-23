"""
Dashboard Registry
Manages registration and retrieval of dashboards
"""
from typing import Dict, List, Optional
from .base import BaseDashboard
import logging

logger = logging.getLogger(__name__)


class DashboardRegistry:
    """Registry for managing all dashboards"""
    
    _dashboards: Dict[str, BaseDashboard] = {}
    
    @classmethod
    def register(cls, dashboard_class):
        """
        Register a dashboard class
        Usage:
            @DashboardRegistry.register
            class MyDashboard(BaseDashboard):
                ...
        """
        instance = dashboard_class()
        cls._dashboards[instance.dashboard_id] = instance
        logger.info(f"Registered dashboard: {instance.dashboard_id} - {instance.title}")
        return dashboard_class
    
    @classmethod
    def get(cls, dashboard_id: str) -> Optional[BaseDashboard]:
        """Get dashboard instance by ID"""
        return cls._dashboards.get(dashboard_id)
    
    @classmethod
    def list_all(cls) -> List[BaseDashboard]:
        """List all registered dashboards"""
        return list(cls._dashboards.values())
    
    @classmethod
    def get_ids(cls) -> List[str]:
        """Get all dashboard IDs"""
        return list(cls._dashboards.keys())
    
    @classmethod
    def exists(cls, dashboard_id: str) -> bool:
        """Check if dashboard exists"""
        return dashboard_id in cls._dashboards
    
    @classmethod
    def get_accessible_dashboards(cls, user_context) -> List[Dict[str, str]]:
        """
        Get list of dashboards accessible by user
        Returns list of dicts with dashboard_id and title
        """
        accessible = []
        for dashboard in cls._dashboards.values():
            if dashboard.check_access(user_context):
                accessible.append({
                    'dashboard_id': dashboard.dashboard_id,
                    'dashboard_title': dashboard.title,
                    'dashboard_description': dashboard.description
                })
        return accessible


