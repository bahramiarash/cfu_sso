"""
LMS Monitoring Dashboard (d8)
Shows LMS usage statistics and monitoring data
"""
from ..base import BaseDashboard
from ..data_providers.lms import LMSDataProvider
from ..registry import DashboardRegistry
from ..context import UserContext
from flask import render_template, make_response
from typing import Dict, Any

@DashboardRegistry.register
class LMSMonitoringDashboard(BaseDashboard):
    """Dashboard for LMS monitoring (d8)"""
    
    def __init__(self):
        super().__init__(
            dashboard_id="d8",
            title="مانیتورینگ LMS",
            description="آمار و اطلاعات مانیتورینگ سیستم مدیریت یادگیری"
        )
        self.data_provider = LMSDataProvider()
        self.cache_ttl = 60  # 1 minute (real-time data)
    
    def get_data(self, context: UserContext, **kwargs) -> Dict[str, Any]:
        """Fetch LMS monitoring data"""
        filters = kwargs.get('filters', {})
        
        return self.data_provider.get_lms_monitoring_data(context, filters)
    
    def render(self, data: Dict[str, Any], context: UserContext):
        """Render dashboard template"""
        template_context = self.get_template_context(data, context)
        
        response = make_response(
            render_template("dashboards/d8.html", **template_context)
        )
        return self.add_no_cache_headers(response)


