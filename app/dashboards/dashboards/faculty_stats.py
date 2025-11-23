"""
Faculty Statistics Dashboard (d1)
Refactored version with context-aware data filtering
"""
from ..base import BaseDashboard
from ..data_providers.faculty import FacultyDataProvider
from ..registry import DashboardRegistry
from ..context import UserContext
from flask import render_template, make_response
from typing import Dict, Any

@DashboardRegistry.register
class FacultyStatsDashboard(BaseDashboard):
    """Dashboard for faculty statistics (d1)"""
    
    def __init__(self):
        super().__init__(
            dashboard_id="d1",
            title="📊 آمار اعضای هیئت علمی (نسخه جدید)",
            description="آمار تفصیلی اعضای هیئت علمی با فیلتر بر اساس سطح دسترسی - معماری جدید"
        )
        self.data_provider = FacultyDataProvider()
        self.cache_ttl = 600  # 10 minutes
    
    def get_data(self, context: UserContext, **kwargs) -> Dict[str, Any]:
        """Fetch faculty statistics with context-aware filtering"""
        filters = kwargs.get('filters', {})
        
        return {
            "sex_data": self.data_provider.get_faculty_by_sex(context, filters),
            "markaz_data": self.data_provider.get_faculty_by_markaz(context, filters),
            "field_data": self.data_provider.get_faculty_by_field(context, filters),
            "type_data": self.data_provider.get_faculty_by_type(context, filters),
            "edugroup_data": self.data_provider.get_faculty_by_edugroup(context, filters),
            "grade_data": self.data_provider.get_faculty_by_grade(context, filters),
            "certificate_data": self.data_provider.get_faculty_by_certificate(context, filters),
            "type_golestan_data": self.data_provider.get_faculty_type_golestan(context, filters),
            "type_sex_data": self.data_provider.get_faculty_by_type_and_sex(context, filters),
        }
    
    def render(self, data: Dict[str, Any], context: UserContext):
        """Render dashboard template"""
        # Prepare template context
        template_context = self.get_template_context(data, context)
        
        # Add filter options for central org users
        if context.data_filters['can_filter_by_province']:
            # Add province list for filtering (can be loaded from database)
            template_context['show_province_filter'] = True
            template_context['show_faculty_filter'] = True
        else:
            template_context['show_province_filter'] = False
            template_context['show_faculty_filter'] = False
        
        # Rename keys to match existing template
        template_context.update({
            'sex_labels': data['sex_data']['labels'],
            'sex_counts': data['sex_data']['counts'],
            'facultytype_labels': data['type_data']['labels'],
            'facultytype_counts': data['type_data']['counts'],
            'markaz_labels': data['markaz_data']['labels'],
            'male_counts': data['markaz_data']['male_counts'],
            'female_counts': data['markaz_data']['female_counts'],
            'field_labels': data['field_data']['labels'],
            'field_counts': data['field_data']['counts'],
            'field_labels_edugroup': data['edugroup_data']['labels'],
            'field_counts_edugroup': data['edugroup_data']['counts'],
            'estekhdamtype_labels': data['type_data']['labels'],
            'estekhdamtype_counts': data['type_data']['counts'],
            'estekhdamtypeGolestan_labels': data['type_golestan_data']['labels'],
            'estekhdamtypeGolestan_counts': data['type_golestan_data']['counts'],
            'grade_labels': data['grade_data']['labels'],
            'grade_counts': data['grade_data']['counts'],
            'madrak_labels': data['certificate_data']['labels'],
            'madrak_counts': data['certificate_data']['counts'],
            'inner_labels': data['type_sex_data']['inner_labels'],
            'inner_data': data['type_sex_data']['inner_data'],
            'outer_labels': data['type_sex_data']['outer_labels'],
            'outer_data': data['type_sex_data']['outer_data'],
        })
        
        response = make_response(
            render_template("dashboards/d1.html", **template_context)
        )
        return self.add_no_cache_headers(response)

