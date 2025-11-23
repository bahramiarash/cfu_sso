"""
Students Dashboard
Dashboard for student-teacher statistics
"""
from typing import Dict, Any
import json
from flask import render_template, make_response
from ..base import BaseDashboard
from ..data_providers.students import StudentsDataProvider
from ..registry import DashboardRegistry
from ..context import UserContext

@DashboardRegistry.register
class StudentsDashboard(BaseDashboard):
    """Dashboard for student-teacher statistics"""
    
    def __init__(self):
        super().__init__(
            dashboard_id="students",
            title="📊 داشبورد اطلاعات دانشجو معلمان (نسخه جدید)",
            description="آمار تفصیلی دانشجو معلمان با فیلتر بر اساس سطح دسترسی - معماری جدید"
        )
        self.data_provider = StudentsDataProvider()
        self.cache_ttl = 600  # 10 minutes
    
    def get_data(self, context: UserContext, **kwargs) -> Dict[str, Any]:
        """Get all data for students dashboard"""
        filters = kwargs.get('filters', {})
        
        return {
            "gender_data": self.data_provider.get_gender_data(context, filters, year_404=False),
            "gender_data_404": self.data_provider.get_gender_data(context, filters, year_404=True),
            "vazeiyat_data": self.data_provider.get_vazeiyat_data(context, filters, year_404=False),
            "vazeiyat_data_404": self.data_provider.get_vazeiyat_data(context, filters, year_404=True),
            "province_vazeiyat_data": self.data_provider.get_province_vazeiyat_data(context, filters),
            "course_data_kardani": self.data_provider.get_course_data_by_grade(context, filters, grade=1),
            "course_data_napeyvaste": self.data_provider.get_course_data_by_grade(context, filters, grade=2),
            "course_data_peyvaste": self.data_provider.get_course_data_by_grade(context, filters, grade=3),
            "course_data_arshad": self.data_provider.get_course_data_by_grade(context, filters, grade=4),
            "grade_data": self.data_provider.get_grade_data(context, filters),
            "province_data": self.data_provider.get_province_data(context, filters),
            "province_year_data": self.data_provider.get_province_year_data(context, filters),
            "province_sex_data": self.data_provider.get_province_sex_data(context, filters),
            "year_data": self.data_provider.get_year_data(context, filters),
            "year_data_grade": self.data_provider.get_year_grade_data(context, filters),
            "course_year_data_kardani": self.data_provider.get_course_year_data(context, filters, grade=1),
            "course_year_data_karshenasi_napeyvaste": self.data_provider.get_course_year_data(context, filters, grade=2),
            "course_year_data_karshenasi_peyvaste": self.data_provider.get_course_year_data(context, filters, grade=3),
            "course_year_data_arshad": self.data_provider.get_course_year_data(context, filters, grade=4),
        }
    
    def render(self, data: Dict[str, Any], context: UserContext):
        """Render students dashboard template"""
        template_context = self.get_template_context(data, context)
        
        # Add filter options for central org users
        if context.data_filters['can_filter_by_province']:
            template_context['show_province_filter'] = True
            template_context['show_faculty_filter'] = True
        else:
            template_context['show_province_filter'] = False
            template_context['show_faculty_filter'] = False
        
        # Convert data to JSON for template (matching old format)
        template_context.update({
            "grouped_data": [],  # Not used in template but kept for compatibility
            "gender_data": json.dumps(data["gender_data"], ensure_ascii=False),
            "gender_data_404": json.dumps(data["gender_data_404"], ensure_ascii=False),
            "vazeiyat_data": json.dumps(data["vazeiyat_data"], ensure_ascii=False),
            "vazeiyat_data_404": json.dumps(data["vazeiyat_data_404"], ensure_ascii=False),
            "province_vazeiyat_data": json.dumps(data["province_vazeiyat_data"], ensure_ascii=False),
            "course_data_kardani": json.dumps(data["course_data_kardani"], ensure_ascii=False),
            "course_data_napeyvaste": json.dumps(data["course_data_napeyvaste"], ensure_ascii=False),
            "course_data_peyvaste": json.dumps(data["course_data_peyvaste"], ensure_ascii=False),
            "course_data_arshad": json.dumps(data["course_data_arshad"], ensure_ascii=False),
            "grade_data": json.dumps(data["grade_data"], ensure_ascii=False),
            "province_data": json.dumps(data["province_data"], ensure_ascii=False),
            "province_year_data": json.dumps(data["province_year_data"], ensure_ascii=False),
            "province_sex_data": json.dumps(data["province_sex_data"], ensure_ascii=False),
            "year_data": json.dumps(data["year_data"], ensure_ascii=False),
            "year_data_grade": json.dumps(data["year_data_grade"], ensure_ascii=False),
            "course_year_data_kardani": json.dumps(data["course_year_data_kardani"], ensure_ascii=False),
            "course_year_data_karshenasi_napeyvaste": json.dumps(data["course_year_data_karshenasi_napeyvaste"], ensure_ascii=False),
            "course_year_data_karshenasi_peyvaste": json.dumps(data["course_year_data_karshenasi_peyvaste"], ensure_ascii=False),
            "course_year_data_arshad": json.dumps(data["course_year_data_arshad"], ensure_ascii=False),
        })
        
        response = make_response(
            render_template("dashboards/students_dashboard.html", **template_context)
        )
        return self.add_no_cache_headers(response)


