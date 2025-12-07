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
        
        # Extended manual mapping (from working dashboard.py code)
        # Persian → English normalized names
        manual_mapping2 = {
            "آذربايجان شرقي": "east azarbaijan",
            "آذربايجان غربي": "west azarbaijan",
            "اردبيل": "ardebil",
            "اصفهان": "esfahan",
            "البرز": "alborz",
            "ايلام": "ilam",
            "بوشهر": "bushehr",
            "تهران": "tehran",
            "چهارمحال بختياري": "chahar mahall and bakhtiari",
            "خراسان جنوبي": "south khorasan",
            "خراسان رضوي": "razavi khorasan",
            "خراسان شمالي": "north khorasan",
            "خوزستان": "khuzestan",
            "زنجان": "zanjan",
            "سمنان": "semnan",
            "سيستان وبلوچستان": "sistan and baluchestan",
            "فارس": "fars",
            "قزوين": "qazvin",
            "قم": "qom",
            "كردستان": "kordestan",
            "كرمان": "kerman",
            "كرمانشاه": "kermanshah",
            "كهگيلويه و بويراحمد": "kohgiluyeh and buyer ahmad",
            "گلستان": "golestan",
            "لرستان": "lorestan",
            "مازندران": "mazandaran",
            "مركزي": "markazi",
            "هرمزگان": "hormozgan",
            "همدان": "hamadan",
            "يزد": "yazd",
            "گيلان": "gilan",
            # Additional variations
            "آذربایجان شرقی": "east azarbaijan",
            "آذربایجان غربی": "west azarbaijan",
            "چهارمحال بختیاری": "chahar mahall and bakhtiari",
            "سیستان وبلوچستان": "sistan and baluchestan",
            "کردستان": "kordestan",
            "کرمان": "kerman",
            "کرمانشاه": "kermanshah",
            "کهگیلویه و بویراحمد": "kohgiluyeh and buyer ahmad",
            "مرکزی": "markazi",
        }
        
        # Normalize the mapping dict (lowercase keys)
        manual_mapping_normalized = {k.strip().lower(): v.lower() for k, v in manual_mapping2.items()}
        
        # Apply the mapping to province names
        self.province_map['province_name_mapped'] = self.province_map['province_name_normalized'].map(
            lambda x: manual_mapping_normalized.get(x, x)  # fallback to original if no match
        )
        
        # Create mapping from mapped names to province codes
        province_map_dict = dict(zip(self.province_map['province_name_mapped'], self.province_map['province_code']))
        
        # Create mapping from shapefile names to province codes
        province_map_normalized = {}
        for shape_name in self.iran_gdf['NAME_1_normalized']:
            # Direct match
            province_code = province_map_dict.get(shape_name)
            
            # If not found, try substring matching
            if province_code is None:
                for mapped_name, code in province_map_dict.items():
                    if mapped_name in shape_name or shape_name in mapped_name:
                        province_code = code
                        break
            
            if province_code is not None:
                province_map_normalized[shape_name] = province_code
        
        self.province_map_dict = province_map_normalized
        self.province_name_dict = dict(
            zip(self.province_map['province_code'], self.province_map['province_name'])
        )
        
        # Log mapping statistics
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Province mapping: {len(province_map_normalized)} provinces mapped out of {len(self.iran_gdf)} shapefile provinces")
        logger.info(f"Database has {len(self.province_map)} provinces")
        if len(province_map_normalized) < len(self.iran_gdf):
            unmatched = set(self.iran_gdf['NAME_1_normalized']) - set(province_map_normalized.keys())
            logger.warning(f"Unmatched shapefile provinces: {list(unmatched)[:10]}")
    
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
        # Reduce margins to minimize empty space
        ax.set_xlim(self.iran_gdf.total_bounds[0], self.iran_gdf.total_bounds[2])
        ax.set_ylim(self.iran_gdf.total_bounds[1], self.iran_gdf.total_bounds[3])
        ax.axis('off')
        
        # Log input data
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Creating map with {len(province_data)} provinces of data")
        logger.info(f"Province map dict has {len(self.province_map_dict)} mappings")
        logger.info(f"Shapefile has {len(self.iran_gdf)} provinces")
        if province_data:
            sample_province = list(province_data.keys())[0]
            logger.info(f"Sample province data (code {sample_province}): {province_data[sample_province]}")
        
        # Log Esfahan (province_code=4) data specifically
        esfahan_data = province_data.get(4, {})
        if esfahan_data:
            logger.info(f"Esfahan (province_code=4) data: Male={esfahan_data.get('1', 0)}, Female={esfahan_data.get('2', 0)}, Total={esfahan_data.get('1', 0) + esfahan_data.get('2', 0)}")
        else:
            logger.warning("Esfahan (province_code=4) data not found in province_data!")
        
        # Add pie charts for each province
        matched_provinces = 0
        unmatched_provinces = []
        provinces_without_data = []
        
        for idx, row in self.iran_gdf.iterrows():
            province_name_norm = row['NAME_1_normalized']
            province_name_original = row['NAME_1']
            province_code = self.province_map_dict.get(province_name_norm)
            
            if province_code is None:
                unmatched_provinces.append(f"{province_name_original} (normalized: {province_name_norm})")
                # Try to find a close match
                for mapped_name, code in self.province_map_dict.items():
                    if province_name_norm in mapped_name or mapped_name in province_name_norm:
                        province_code = code
                        logger.debug(f"Found close match for {province_name_original}: {mapped_name} -> {code}")
                        break
                
                if province_code is None:
                    continue  # Skip provinces without mapping
            
            # Log Esfahan mapping specifically
            if province_code == 4 or 'esfahan' in province_name_norm:
                logger.info(f"Esfahan mapping check: shapefile_name='{province_name_original}' (normalized='{province_name_norm}'), province_code={province_code}")
            
            data = province_data.get(province_code, {})
            # Ensure we get the correct values - '1' for male, '2' for female
            male_count = int(data.get('1', 0))
            female_count = int(data.get('2', 0))
            values = [male_count, female_count]
            
            # Log Esfahan data specifically with detailed breakdown
            if province_code == 4:
                logger.info(f"Esfahan (code=4) detailed data check:")
                logger.info(f"  - Raw data dict: {data}")
                logger.info(f"  - Male (key '1'): {male_count}")
                logger.info(f"  - Female (key '2'): {female_count}")
                logger.info(f"  - Values array: {values}")
                logger.info(f"  - Total: {sum(values)}")
                if sum(values) > 0:
                    logger.info(f"  - Expected percentages: Male={(male_count/sum(values)*100):.1f}%, Female={(female_count/sum(values)*100):.1f}%")
                if sum(values) == 0:
                    logger.warning("Esfahan (code=4) has no data! This should not happen.")
            
            # Skip if no data for this province
            if sum(values) == 0:
                provinces_without_data.append(f"{province_name_original} (code: {province_code})")
                continue
            
            matched_provinces += 1
            centroid = row['geometry'].centroid
            try:
                # Verify values before rendering (especially for Esfahan)
                if province_code == 4:
                    logger.info(f"Esfahan rendering: values={values}, sum={sum(values)}, male_pct={(values[0]/sum(values)*100) if sum(values) > 0 else 0:.1f}%, female_pct={(values[1]/sum(values)*100) if sum(values) > 0 else 0:.1f}%")
                
                pie_ax = inset_axes(
                    ax,
                    width=0.65,
                    height=1.65,
                    loc='center',
                    bbox_to_anchor=(centroid.x, centroid.y),
                    bbox_transform=ax.transData,
                    borderpad=15
                )
                
                # matplotlib's pie() function automatically calculates percentages correctly from values
                # For Esfahan: values=[29, 29] will show 50% and 50%
                # The autopct='%1.0f%%' format string will display the percentage that matplotlib calculates
                # which is based on the actual values, so it should be correct
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
                logger.warning(f"Error rendering pie chart for {province_name_original} (code: {province_code}): {e}")
                import traceback
                logger.warning(f"Traceback: {traceback.format_exc()}")
                continue
        
        # Log mapping statistics
        logger.info(f"Map rendering complete: {matched_provinces} provinces with pie charts rendered")
        logger.info(f"Unmatched provinces (no mapping): {len(unmatched_provinces)}")
        logger.info(f"Provinces without data: {len(provinces_without_data)}")
        if unmatched_provinces:
            logger.warning(f"Unmatched provinces: {unmatched_provinces}")
        if provinces_without_data:
            logger.info(f"Provinces without data: {provinces_without_data}")
        
        # Add legend
        patches = [Patch(color=colors[i], label=reshape_rtl(label)) 
                  for i, label in enumerate(legend_labels)]
        ax.legend(
            handles=patches,
            loc='lower center',
            bbox_to_anchor=(0.5, 0.02),
            ncol=len(legend_labels),
            frameon=True
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
        
        # Apply tight layout before saving to minimize empty space
        plt.tight_layout(pad=1.0)
        
        # Convert to BytesIO with tight bounding box to remove empty space
        img = io.BytesIO()
        fig.savefig(img, format='png', bbox_inches='tight', pad_inches=0.2, dpi=100)
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


