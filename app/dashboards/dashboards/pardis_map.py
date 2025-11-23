"""
Pardis Map Dashboard (d3)
Shows pardis distribution by province on a map
"""
from ..base import BaseDashboard
from ..data_providers.pardis import PardisDataProvider
from ..visualizations.maps import MapBuilder
from ..registry import DashboardRegistry
from ..context import UserContext
from flask import render_template, make_response
from typing import Dict, Any
import json
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
import io
import base64
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
import matplotlib.patches as mpatches
import matplotlib.font_manager as font_manager
import jdatetime
from dashboards.config import DashboardConfig
from dashboards.utils import reshape_rtl

@DashboardRegistry.register
class PardisMapDashboard(BaseDashboard):
    """Dashboard for pardis map by province (d3)"""
    
    def __init__(self):
        super().__init__(
            dashboard_id="d3",
            title="نقشه توزیع پردیس‌ها",
            description="نقشه توزیع پردیس‌ها، مراکز و دانشکده‌ها"
        )
        self.data_provider = PardisDataProvider()
        self.cache_ttl = 600  # 10 minutes
    
    def get_data(self, context: UserContext, **kwargs) -> Dict[str, Any]:
        """Fetch pardis data by province with context filtering"""
        filters = kwargs.get('filters', {})
        
        # Get pardis data
        province_data = self.data_provider.get_pardis_by_province(context, filters)
        
        return {
            "province_data": province_data
        }
    
    def render(self, data: Dict[str, Any], context: UserContext):
        """Render map with table"""
        province_data = data['province_data']
        
        # Load shapefile and province mapping
        iran_gdf = gpd.read_file(str(DashboardConfig.IRAN_SHAPEFILE))[['NAME_1', 'geometry']]
        iran_gdf['NAME_1'] = iran_gdf['NAME_1'].str.strip()
        iran_gdf['NAME_1_normalized'] = iran_gdf['NAME_1'].str.lower()
        
        # Load province mapping
        import sqlite3
        import pandas as pd
        conn = sqlite3.connect(DashboardConfig.FACULTY_DB)
        province_map = pd.read_sql_query("SELECT province_code, province_name FROM province", conn)
        province_map['province_name_normalized'] = province_map['province_name'].str.strip().str.lower()
        conn.close()
        
        # Apply mapping
        mappings = DashboardConfig.get_province_mappings()
        normalized_map = {k.strip().lower(): v for k, v in mappings.items()}
        province_map['province_name_mapped'] = province_map['province_name_normalized'].map(
            lambda x: normalized_map.get(x, x)
        )
        
        province_map_dict = dict(zip(province_map['province_name_mapped'], province_map['province_code']))
        province_name_dict = dict(zip(province_map['province_code'], province_map['province_name']))
        
        # Create map
        fig, ax = plt.subplots(figsize=(9, 8))
        iran_gdf.plot(ax=ax, color="#f9f9f9", edgecolor="#aaa")
        ax.set_axis_off()
        
        font_path = str(DashboardConfig.BASE_DIR / 'static' / 'fonts' / 'Vazir.ttf')
        try:
            font_prop = font_manager.FontProperties(fname=font_path)
        except:
            font_prop = None
        
        today_shamsi = jdatetime.date.today().strftime('%Y/%m/%d')
        ax.text(0.5, 0.97, reshape_rtl(f"تاریخ: {today_shamsi}"),
                transform=ax.transAxes, ha='center', fontsize=13, fontproperties=font_prop)
        
        # Add pie charts
        for idx, row in iran_gdf.iterrows():
            province_name_norm = row['NAME_1_normalized'].lower()
            province_code = province_map_dict.get(province_name_norm)
            
            if not province_code:
                continue
            
            counts = province_data.get(province_code, {})
            values = [counts.get(1, 0), counts.get(2, 0), counts.get(3, 0), counts.get(4, 0)]
            
            if sum(values) == 0:
                continue
            
            centroid = row['geometry'].centroid
            ax_inset = inset_axes(
                ax, width=0.4, height=0.4, loc='center',
                bbox_to_anchor=(centroid.x, centroid.y),
                bbox_transform=ax.transData, borderpad=0.1
            )
            ax_inset.pie(
                [x for x in values if x != 0],
                labels=[x for x in values if x != 0],
                startangle=90,
                colors=['#66c2a5', '#fc8d62', '#8da0cb', '#e78ac3']
            )
            ax_inset.set_aspect("equal")
        
        # Add legend
        patches = [
            mpatches.Patch(color='#66c2a5', label=reshape_rtl('پردیس')),
            mpatches.Patch(color='#fc8d62', label=reshape_rtl('مرکز')),
            mpatches.Patch(color='#8da0cb', label=reshape_rtl('دانشکده')),
        ]
        ax.legend(handles=patches, loc='lower center', ncol=4,
                 bbox_to_anchor=(0.5, -0.05), frameon=False)
        
        # Convert to base64
        buf = io.BytesIO()
        canvas = FigureCanvas(fig)
        canvas.print_png(buf)
        buf.seek(0)
        encoded_img = base64.b64encode(buf.read()).decode('utf-8')
        plt.close(fig)
        
        # Prepare table data
        d3_data = []
        row_number = 1
        for province_code, counts in province_data.items():
            province_name_fa = province_name_dict.get(province_code, "نامشخص")
            d3_data.append({
                "row": row_number,
                "province": province_name_fa,
                "pardis_count": counts.get(1, 0),
                "markaz_count": counts.get(2, 0),
                "daneshkade_count": counts.get(3, 0),
                "other_count": counts.get(4, 0),
            })
            row_number += 1
        
        d3_json = json.dumps(d3_data, ensure_ascii=False)
        
        template_context = self.get_template_context({
            "image_data": encoded_img,
            "d3_data": d3_json
        }, context)
        
        response = make_response(
            render_template("dashboards/d3.html", **template_context)
        )
        return self.add_no_cache_headers(response)


