"""
Faculty Map Dashboard (d2)
Shows faculty distribution by province on a map
"""
from ..base import BaseDashboard
from ..data_providers.faculty import FacultyDataProvider
from ..visualizations.maps import MapBuilder
from ..registry import DashboardRegistry
from ..context import UserContext
from flask import send_file
from typing import Dict, Any
from collections import defaultdict

@DashboardRegistry.register
class FacultyMapDashboard(BaseDashboard):
    """Dashboard for faculty map by province (d2)"""
    
    def __init__(self):
        super().__init__(
            dashboard_id="d2",
            title="نقشه توزیع اعضای هیئت علمی",
            description="نقشه توزیع اعضای هیئت علمی به تفکیک جنسیت در هر استان"
        )
        self.data_provider = FacultyDataProvider()
        self.map_builder = MapBuilder()
        self.cache_ttl = 600  # 10 minutes
    
    def get_data(self, context: UserContext, **kwargs) -> Dict[str, Any]:
        """Fetch faculty data by province with context filtering"""
        filters = kwargs.get('filters', {})
        
        # Get province data with gender breakdown
        province_data = self.data_provider.get_faculty_by_province(context, filters)
        
        return {
            "province_data": province_data
        }
    
    def render(self, data: Dict[str, Any], context: UserContext):
        """Render map as PNG image"""
        province_data = data['province_data']
        
        # Create map with pie charts
        img = self.map_builder.create_province_map_with_pie_charts(
            province_data=province_data,
            title="توزیع اعضای هیات علمی به تفکیک جنسیت در هر استان",
            colors=['#36A2EB', '#FF6384'],
            legend_labels=['مرد', 'زن']
        )
        
        response = send_file(img, mimetype='image/png')
        return self.add_no_cache_headers(response)


