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


def persian_sort_key(text: str) -> list:
    """
    Create a sort key for Persian text based on Persian alphabet order
    Persian alphabet order:
    آ – ا, ب, پ, ت, ث, ج, چ, ح, خ, د, ذ, ر, ز, ژ, س, ش, ص, ض, ط, ظ, ع, غ, ف, ق, ک-ك, گ, ل, م, ن, و, ه, ی-ي
    """
    # Persian alphabet order mapping
    persian_order = {
        'آ': 1, 'ا': 1,  # آ and ا have same priority
        'ب': 2,
        'پ': 3,
        'ت': 4,
        'ث': 5,
        'ج': 6,
        'چ': 7,
        'ح': 8,
        'خ': 9,
        'د': 10,
        'ذ': 11,
        'ر': 12,
        'ز': 13,
        'ژ': 14,
        'س': 15,
        'ش': 16,
        'ص': 17,
        'ض': 18,
        'ط': 19,
        'ظ': 20,
        'ع': 21,
        'غ': 22,
        'ف': 23,
        'ق': 24,
        'ک': 25, 'ك': 25,  # ک and ك have same priority
        'گ': 26,
        'ل': 27,
        'م': 28,
        'ن': 29,
        'و': 30,
        'ه': 31,
        'ی': 32, 'ي': 32,  # ی and ي have same priority
    }
    
    # Convert text to list of character priorities
    result = []
    for char in text:
        if char in persian_order:
            result.append(persian_order[char])
        else:
            # For non-Persian characters, use their Unicode value
            result.append(ord(char) + 1000)  # Offset to put them after Persian chars
    
    return result

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
        
        # Get province names from database
        province_names = self.data_provider.get_province_names()
        
        # Calculate total faculty count for the country
        total_country = sum(
            data.get('1', 0) + data.get('2', 0) 
            for data in province_data.values()
        )
        
        # Prepare table data
        table_data = []
        for province_code in sorted(province_data.keys()):
            data = province_data[province_code]
            male_count = data.get('1', 0)
            female_count = data.get('2', 0)
            total_province = male_count + female_count
            
            if total_province == 0:
                continue  # Skip provinces with no data
            
            # Calculate percentages
            female_percent = (female_count / total_province * 100) if total_province > 0 else 0
            male_percent = (male_count / total_province * 100) if total_province > 0 else 0
            country_percent = (total_province / total_country * 100) if total_country > 0 else 0
            
            province_name = province_names.get(province_code, f"استان {province_code}")
            
            table_data.append({
                'province_code': province_code,
                'province_name': province_name,
                'total': total_province,
                'male_count': male_count,
                'female_count': female_count,
                'female_percent': female_percent,
                'male_percent': male_percent,
                'country_percent': country_percent
            })
        
        # Sort by province name (Persian) ascending using Persian alphabet order
        table_data.sort(key=lambda x: persian_sort_key(x['province_name']))
        
        # Log data for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"FacultyMapDashboard.get_data: Retrieved data for {len(province_data)} provinces")
        logger.info(f"Total country faculty count: {total_country}")
        if province_data:
            sample_province = list(province_data.keys())[0]
            logger.info(f"Sample province {sample_province}: {province_data[sample_province]}")
        else:
            logger.warning("FacultyMapDashboard.get_data: No province data retrieved!")
        
        return {
            "province_data": province_data,
            "table_data": table_data,
            "total_country": total_country
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
            "image_data": encoded_img,
            "table_data": data.get('table_data', []),
            "total_country": data.get('total_country', 0)
        })
        
        # Render template
        response = make_response(
            render_template("dashboards/d2.html", **template_context)
        )
        return self.add_no_cache_headers(response)


