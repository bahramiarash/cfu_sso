"""
Map Visualization Components
Reusable components for creating geographic maps
"""
import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.patches import Patch
import matplotlib.font_manager as font_manager
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
from typing import Dict, List, Optional, Tuple
from dashboards.config import DashboardConfig
from dashboards.utils import reshape_rtl
import jdatetime
import io
from flask import send_file

class MapBuilder:
    """Builder for geographic maps with pie charts"""
    
    def __init__(self, shapefile_path: Optional[str] = None):
        self.shapefile_path = shapefile_path or str(DashboardConfig.IRAN_SHAPEFILE)
        self.iran_gdf = None
        self.province_map = None
        self.province_map_dict = None
        self.province_name_dict = None
        self._load_shapefile()
        self._load_province_mapping()
    
    def _load_shapefile(self):
        """Load Iran shapefile"""
        self.iran_gdf = gpd.read_file(self.shapefile_path)[['NAME_1', 'geometry']]
        self.iran_gdf['NAME_1'] = self.iran_gdf['NAME_1'].str.strip()
        self.iran_gdf['NAME_1_normalized'] = self.iran_gdf['NAME_1'].str.lower()
    
    def _load_province_mapping(self):
        """Load province mapping from database"""
        import sqlite3
        conn = sqlite3.connect(DashboardConfig.FACULTY_DB)
        self.province_map = pd.read_sql_query(
            "SELECT province_code, province_name FROM province ORDER BY province_name",
            conn
        )
        conn.close()
        
        self.province_map['province_name_normalized'] = (
            self.province_map['province_name'].str.strip().str.lower()
        )
        
        # Apply mapping from config
        mappings = DashboardConfig.get_province_mappings()
        reverse_mapping = {v.lower(): k for k, v in mappings.items()}
        
        # Create mapping dictionaries
        province_map_normalized = {}
        for _, row in self.province_map.iterrows():
            province_name_fa = row['province_name']
            province_name_norm = row['province_name_normalized']
            province_code = row['province_code']
            
            # Try to match with shapefile names
            for shape_name in self.iran_gdf['NAME_1_normalized']:
                if province_name_norm in shape_name or shape_name in province_name_norm:
                    province_map_normalized[shape_name] = province_code
                    break
        
        self.province_map_dict = province_map_normalized
        self.province_name_dict = dict(
            zip(self.province_map['province_code'], self.province_map['province_name'])
        )
    
    def create_province_map_with_pie_charts(
        self,
        province_data: Dict[int, Dict[str, int]],
        title: str,
        colors: List[str] = None,
        legend_labels: List[str] = None,
        figsize: Tuple[int, int] = (15, 26)
    ) -> io.BytesIO:
        """
        Create map with pie charts for each province
        
        Args:
            province_data: Dict mapping province_code to data dict
                          e.g., {1: {'1': 100, '2': 50}}
            title: Map title
            colors: List of colors for pie chart segments
            legend_labels: List of labels for legend
            figsize: Figure size tuple
        
        Returns:
            BytesIO object containing PNG image
        """
        if colors is None:
            colors = ['#36A2EB', '#FF6384']
        if legend_labels is None:
            legend_labels = ['مرد', 'زن']
        
        fig, ax = plt.subplots(figsize=figsize)
        self.iran_gdf.plot(ax=ax, color='#eee', edgecolor='#ccc')
        fig.subplots_adjust(top=1.37)
        plt.tight_layout(rect=[0, 0.15, 1, 0.1])
        
        # Add pie charts for each province
        for idx, row in self.iran_gdf.iterrows():
            province_name_norm = row['NAME_1_normalized']
            province_code = self.province_map_dict.get(province_name_norm)
            
            if province_code is None:
                values = [1, 1]  # Default values
            else:
                data = province_data.get(province_code, {})
                values = [
                    int(data.get('1', 0)),
                    int(data.get('2', 0))
                ]
            
            if sum(values) == 0:
                values = [1, 1]
            
            centroid = row['geometry'].centroid
            try:
                pie_ax = inset_axes(
                    ax,
                    width=0.65,
                    height=1.65,
                    loc='center',
                    bbox_to_anchor=(centroid.x, centroid.y),
                    bbox_transform=ax.transData,
                    borderpad=15
                )
                pie_ax.pie(
                    values,
                    labels=None,
                    colors=colors,
                    explode=(0.1, 0),
                    autopct='%1.0f%%',
                    startangle=90
                )
                pie_ax.axis('equal')
            except Exception as e:
                print(f"Error rendering pie chart for {province_name_norm}: {e}")
                continue
        
        # Add legend
        patches = [Patch(color=colors[i], label=reshape_rtl(label)) 
                  for i, label in enumerate(legend_labels)]
        ax.legend(
            handles=patches,
            loc='lower center',
            bbox_to_anchor=(0.5, -0.05),
            ncol=len(legend_labels)
        )
        
        # Add title
        font_path = str(DashboardConfig.BASE_DIR / 'static' / 'fonts' / 'Vazir.ttf')
        try:
            font_prop = font_manager.FontProperties(fname=font_path)
        except:
            font_prop = None
        
        ax.set_title(reshape_rtl(title), fontproperties=font_prop, fontsize=24)
        
        today_shamsi = jdatetime.date.today().strftime('%Y/%m/%d')
        ax.text(
            0.5, 0.97,
            reshape_rtl(f"تاریخ: {today_shamsi}"),
            transform=ax.transAxes,
            ha='center',
            fontsize=16,
            fontproperties=font_prop
        )
        ax.axis('off')
        
        # Convert to BytesIO
        img = io.BytesIO()
        FigureCanvas(fig).print_png(img)
        img.seek(0)
        plt.close(fig)
        return img
    
    def create_province_table_data(
        self,
        province_data: Dict[int, Dict[str, int]]
    ) -> List[List]:
        """
        Create table data for province statistics
        
        Returns:
            List of rows, first row is headers
        """
        # Calculate national total
        national_total = sum(
            sum(data.values()) for data in province_data.values()
        )
        
        table_data = []
        row_number = 1
        total_male = 0
        total_female = 0
        total_sum = 0
        
        # Get reverse mapping
        mappings = DashboardConfig.get_province_mappings()
        reverse_mapping = {v.lower(): k for k, v in mappings.items()}
        
        # Collect province rows
        province_rows = []
        for idx, row in self.iran_gdf.iterrows():
            province_name_norm = row['NAME_1_normalized']
            province_name_fa = reverse_mapping.get(province_name_norm, row['NAME_1'])
            
            province_rows.append({
                'idx': idx,
                'row': row,
                'province_name_fa': province_name_fa,
                'province_name_norm': province_name_norm
            })
        
        # Sort provinces
        province_rows_sorted = sorted(
            province_rows,
            key=lambda x: x['province_name_fa']
        )
        
        # Build table data
        for item in province_rows_sorted:
            province_name_norm = item['province_name_norm']
            province_name_fa = reshape_rtl(item['province_name_fa'])
            province_code = self.province_map_dict.get(province_name_norm)
            
            if province_code is None:
                male_count, female_count = 0, 0
            else:
                data = province_data.get(province_code, {})
                male_count = int(data.get('1', 0))
                female_count = int(data.get('2', 0))
            
            total = male_count + female_count
            total_male += male_count
            total_female += female_count
            total_sum += total
            
            male_percent = (male_count / total * 100) if total > 0 else 0
            female_percent = (female_count / total * 100) if total > 0 else 0
            national_percent = (total / national_total * 100) if national_total > 0 else 0
            
            table_data.append([
                f"{male_percent:.0f}%",
                f"{female_percent:.0f}%",
                f"{male_count:,}",
                f"{female_count:,}",
                f"{total:,}",
                f"{national_percent:.1f}%",
                province_name_fa,
                row_number,
            ])
            row_number += 1
        
        # Add total row
        table_data.append([
            f"{(100*total_male/total_sum):.0f}%" if total_sum > 0 else "0%",
            f"{(100*total_female/total_sum):.0f}%" if total_sum > 0 else "0%",
            f"{total_male:,}",
            f"{total_female:,}",
            f"{total_sum:,}",
            "",
            reshape_rtl("جمع کل"),
            "",
        ])
        
        # Add headers
        headers = [
            reshape_rtl("درصد مرد"),
            reshape_rtl("درصد زن"),
            reshape_rtl("تعداد هیات علمی مرد"),
            reshape_rtl("تعداد هیات علمی زن"),
            reshape_rtl("کل هیات علمی استان"),
            reshape_rtl("%استان از کل"),
            reshape_rtl("استان"),
            reshape_rtl("ردیف")
        ]
        table_data.insert(0, headers)
        
        return table_data


