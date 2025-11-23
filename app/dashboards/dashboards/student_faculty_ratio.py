"""
Student-Faculty Ratio Dashboard (d7)
Shows ratio of students to faculty over time
"""
from ..base import BaseDashboard
from ..data_providers.students import StudentsDataProvider
from ..registry import DashboardRegistry
from ..context import UserContext
from flask import render_template, make_response
from typing import Dict, Any

@DashboardRegistry.register
class StudentFacultyRatioDashboard(BaseDashboard):
    """Dashboard for student-faculty ratio (d7)"""
    
    def __init__(self):
        super().__init__(
            dashboard_id="d7",
            title="نسبت دانشجو به استاد",
            description="نمودار نسبت تعداد دانشجویان به اعضای هیئت علمی بر اساس مقطع تحصیلی"
        )
        self.data_provider = StudentsDataProvider()
        self.cache_ttl = 600  # 10 minutes
    
    def get_data(self, context: UserContext, **kwargs) -> Dict[str, Any]:
        """Fetch student-faculty ratio data with context filtering"""
        filters = kwargs.get('filters', {})
        
        chart_data = self.data_provider.get_students_by_grade_and_year(context, filters)
        
        return {
            "labels": chart_data["labels"],
            "datasets": chart_data["datasets"]
        }
    
    def render(self, data: Dict[str, Any], context: UserContext):
        """Render dashboard template"""
        template_context = self.get_template_context(data, context)
        
        response = make_response(
            render_template("dashboards/d7.html", **template_context)
        )
        return self.add_no_cache_headers(response)


