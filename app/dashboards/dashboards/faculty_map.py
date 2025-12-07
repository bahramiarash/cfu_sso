"""
Faculty Map Dashboard (d2)
Shows faculty distribution by province on a map
"""
from ..base import BaseDashboard
from ..data_providers.faculty import FacultyDataProvider
from ..visualizations.maps import MapBuilder
from ..registry import DashboardRegistry
from ..context import UserContext
from flask import render_template, make_response
from typing import Dict, Any
from collections import defaultdict
import base64

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
        
        # Log data for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"FacultyMapDashboard.get_data: Retrieved data for {len(province_data)} provinces")
        if province_data:
            sample_province = list(province_data.keys())[0]
            logger.info(f"Sample province {sample_province}: {province_data[sample_province]}")
        else:
            logger.warning("FacultyMapDashboard.get_data: No province data retrieved!")
        
        return {
            "province_data": province_data
        }
    
    def render(self, data: Dict[str, Any], context: UserContext):
        """Render map template with base64 encoded image"""
        province_data = data['province_data']
        
        # Create map with pie charts
        img_bytesio = self.map_builder.create_province_map_with_pie_charts(
            province_data=province_data,
            title="توزیع اعضای هیات علمی به تفکیک جنسیت در هر استان",
            colors=['#36A2EB', '#FF6384'],
            legend_labels=['مرد', 'زن']
        )
        
        # Convert to base64
        img_bytesio.seek(0)
        encoded_img = base64.b64encode(img_bytesio.read()).decode('utf-8')
        
        # Prepare template context
        template_context = self.get_template_context(data, context)
        template_context.update({
            "image_data": encoded_img
        })
        
        # Render template
        response = make_response(
            render_template("dashboards/d2.html", **template_context)
        )
        return self.add_no_cache_headers(response)


