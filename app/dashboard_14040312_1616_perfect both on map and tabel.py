from flask import Blueprint, session, render_template, abort, redirect, url_for, jsonify, request
from dashboards_config import DASHBOARDS
import logging
import sqlite3
import os
from auth_utils import requires_auth
from flask import make_response
from collections import defaultdict
import geopandas as gpd
import pandas as pd
import matplotlib
# Set non-interactive backend to avoid GUI issues
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
import io
import base64
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from flask import send_file
import arabic_reshaper
from bidi.algorithm import get_display
from matplotlib import font_manager
import jdatetime

def reshape_rtl(text):
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = "C:\\services\\cert2\\app\\access_control.db"
bp = Blueprint('dashboard', __name__)

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboards")

def get_accessible_dashboards():
    access_levels = session.get("access_level", [])
    if isinstance(access_levels, str):
        access_levels = [access_levels]

    dashboards = []
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for level in access_levels:
        cursor.execute("""
            SELECT d.dashboard_id, d.dashboard_title
            FROM dashboards d
            JOIN role_dashboard rd ON d.id = rd.dashboard_id
            JOIN roles r ON r.id = rd.role_id
            WHERE r.name = ?
        """, (level,))
        rows = cursor.fetchall()
        for dashboard_id, dashboard_title in rows:
            dashboards.append({
                "dashboard_id": dashboard_id,
                "dashboard_title": dashboard_title or dashboard_id.replace('_', ' ').title()
            })

    conn.close()
    return dashboards

@dashboard_bp.route("/")
@requires_auth
def dashboard_list():
    # Enforce authentication
    if 'user_info' not in session:
        logging.info("User not authenticated, redirecting to login")
        return redirect(url_for('login'))

    user_info = session['user_info']
    level = user_info.get('usertype')

    # Store usertype in session as access_level
    session['access_level'] = [level] if isinstance(level, str) else level

    dashboards = get_accessible_dashboards()
    response = make_response(render_template("dashboard_list.html", dashboards=dashboards, user=user_info))

    # Add no-cache headers
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@dashboard_bp.route("/<dashboard_id>")
@requires_auth
def show_dashboard(dashboard_id):
    accessible_dashboards = get_accessible_dashboards()

    # Fix: Extract just the IDs from the dashboards
    accessible_ids = [d['dashboard_id'] for d in accessible_dashboards]

    if dashboard_id not in accessible_ids:
        return render_template("error.html", error="Unauthorized access"), 403

    try:
        response = make_response(render_template(f"dashboards/{dashboard_id}.html"))

        # Add no-cache headers
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    except Exception as e:
        return render_template("error.html", error="Dashboard not found"), 404

@dashboard_bp.route("/d1")
@requires_auth
def dashboard_d1():
    DB_PATH2 = "C:\\services\\cert2\\app\\fetch_data\\faculty_data.db"
    conn = sqlite3.connect(DB_PATH2)
    cursor = conn.cursor()

    # Sex chart: Group by Sex
    cursor.execute("""
        SELECT 
            CASE sex
                WHEN 1 THEN 'مرد'
                WHEN 2 THEN 'زن'
                ELSE 'نامشخص'
            END AS sex_label,				
            COUNT(*) as faculty_count
        FROM faculty
        GROUP BY sex
        ORDER BY faculty_count DESC
    """)
    sex_data = cursor.fetchall()
    sex_labels = [row[0] for row in sex_data]  # 'مرد', 'زن', etc.
    sex_counts = [row[1] for row in sex_data]  # 120, 85, etc.


    # First chart: Group by Markaz
    cursor.execute("""
    SELECT 
        f.markaz,
        CASE f.sex
            WHEN 1 THEN 'مرد'
            WHEN 2 THEN 'زن'
            ELSE 'نامشخص'
        END AS sex_label,
        COUNT(*) AS faculty_count,
        totals.total_faculty
    FROM faculty f
    JOIN (
        SELECT code_markaz, COUNT(*) AS total_faculty
        FROM faculty
        WHERE sex IN (1, 2)
        GROUP BY code_markaz
    ) AS totals ON f.code_markaz = totals.code_markaz
    GROUP BY f.code_markaz, f.sex
    ORDER BY totals.total_faculty DESC;

    """)
    rows = cursor.fetchall()

    # ساخت دیکشنری: {مرکز: {جنسیت: تعداد}}
    grouped_data = defaultdict(lambda: {'زن': 0, 'مرد': 0, 'نامشخص': 0})

    for markaz, sex_label, count, _ in rows:
        markaz = markaz or "نامشخص"
        grouped_data[markaz][sex_label] += count

    # ساخت لیست برای قالب Chart.js
    markaz_labels = list(grouped_data.keys())
    male_counts = [grouped_data[m]['مرد'] for m in markaz_labels]
    female_counts = [grouped_data[m]['زن'] for m in markaz_labels]

    # Second chart: Group by Field
    cursor.execute("""
        SELECT field, COUNT(*) as faculty_count
        FROM faculty
        GROUP BY field
        ORDER BY faculty_count DESC
    """)
    field_data = cursor.fetchall()
    field_labels = [row[0] if row[0] else "نامشخص" for row in field_data]
    field_counts = [row[1] for row in field_data]

    # Third chart: Group by estekhdamtype
    cursor.execute("""
        SELECT estekhdamtype_title, COUNT(*) as faculty_count
        FROM faculty
        GROUP BY estekhdamtype
        ORDER BY faculty_count DESC
    """)
    estekhdamtype_data = cursor.fetchall()
    estekhdamtype_labels = [row[0] if row[0] else "نامشخص" for row in estekhdamtype_data]
    estekhdamtype_counts = [row[1] for row in estekhdamtype_data]

    # Fifth chart: Group by estekhdamtype and sex
    # Run the query
    cursor.execute("""
        SELECT estekhdamtype_title,
            CASE sex
                WHEN 1 THEN 'مرد'
                WHEN 2 THEN 'زن'
                ELSE 'نامشخص'
            END AS sex_label,
            COUNT(*) AS faculty_count
        FROM faculty
        GROUP BY estekhdamtype_title, sex
        ORDER BY estekhdamtype_title, sex;
    """)
    rows = cursor.fetchall()

    # ساختار دسته‌بندی‌شده
    grouped_data = defaultdict(lambda: defaultdict(int))

    for row in rows:
        estekhdam = row[0] or "نامشخص"
        sex = row[1]
        count = row[2]
        grouped_data[estekhdam][sex] += count

    # سطح اول (نوع استخدام)
    inner_labels = []
    inner_data = []

    # سطح دوم (جنسیت در هر نوع استخدام)
    outer_labels = []
    outer_data = []

    for estekhdam_type, sexes in grouped_data.items():
        total = sum(sexes.values())
        inner_labels.append(estekhdam_type)
        inner_data.append(total)

        for sex_label, count in sexes.items():
            outer_labels.append(f"{estekhdam_type} - {sex_label}")
            outer_data.append(count)

    conn.close()

    response = make_response(render_template("dashboards/d1.html",
                            sex_labels=sex_labels,
                            sex_counts=sex_counts,
                            markaz_labels=markaz_labels,
                            male_counts=male_counts,
                            female_counts=female_counts,
                            field_labels=field_labels,
                            field_counts=field_counts,
                            estekhdamtype_labels=estekhdamtype_labels,
                            estekhdamtype_counts=estekhdamtype_counts,
                            inner_labels=inner_labels,           # for inner pie ring (estekhdam types)
                            inner_data=inner_data,
                            outer_labels=outer_labels,           # for outer pie ring (sex breakdown)
                            outer_data=outer_data))

    # Add no-cache headers
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@dashboard_bp.route('/d2')
@requires_auth
def map_dashboard():
    import geopandas as gpd
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
    import io
    from flask import send_file
    from shapely.geometry import Point
    import pandas as pd
    from collections import defaultdict
    import matplotlib.patches as mpatches
    import matplotlib.font_manager as font_manager
    import jdatetime
    import sqlite3
    from matplotlib.axes import Axes
    from mpl_toolkits.axes_grid1.inset_locator import inset_axes

    # Load shapefile
    iran_gdf = gpd.read_file("data/iran_shapefile/gadm41_IRN_1.shp")[['NAME_1', 'geometry']]
    iran_gdf['NAME_1'] = iran_gdf['NAME_1'].str.strip()
    iran_gdf['NAME_1_normalized'] = iran_gdf['NAME_1'].str.lower()

    # Connect to DB
    DB_PATH2 = "C:\\services\\cert2\\app\\fetch_data\\faculty_data.db"
    conn = sqlite3.connect(DB_PATH2)

    # Fetch province mappings
    province_map = pd.read_sql_query("SELECT province_code, province_name FROM province ORDER BY  province_name", conn)
    province_map['province_name_normalized'] = province_map['province_name'].str.strip().str.lower()
    # logger.info(province_map['province_name_normalized'])
    # Manual mapping for Persian → English normalized names
    manual_mapping = {
        'تهران': 'tehran',
        'خراسان رضوی': 'razavi khorasan',
        'اصفهان': 'esfahan',
        'فارس': 'fars',
        'خوزستان': 'khuzestan',
        'آذربایجان شرقی': 'east azarbaijan',
        'آذربایجان غربی': 'west azarbaijan',
        'کرمان': 'kerman',
        'سیستان و بلوچستان': 'sistan and baluchestan',
        'گیلان': 'gilan',
        'مازندران': 'mazandaran',
        'البرز': 'alborz',
        'قم': 'qom',
        'یزد': 'yazd',
        'همدان': 'hamadan',
        'کرمانشاه': 'kermanshah',
        'لرستان': 'lorestan',
        'هرمزگان': 'hormozgan',
        'چهارمحال و بختیاری': 'chahar mahall and bakhtiari',
        'کردستان': 'kordestan',
        'گلستان': 'golestan',
        'زنجان': 'zanjan',
        'سمنان': 'semnan',
        'قزوین': 'qazvin',
        'اردبیل': 'ardebil',
        'مرکزی': 'markazi',
        'بوشهر': 'bushehr',
        'کهگیلویه و بویراحمد': 'kohgiluyeh and buyer ahmad',
        'ایلام': 'ilam',
        'خراسان شمالی': 'north khorasan',
        'خراسان جنوبی': 'south khorasan'
    }


    # Apply mapping to shapefile to ensure Persian names
    iran_gdf['province_name_fa'] = iran_gdf['NAME_1_normalized'].map(manual_mapping).fillna(iran_gdf['NAME_1'])


    # Invert mapping: English normalized → Persian
    reverse_mapping = {v.lower(): k for k, v in manual_mapping.items()}

    # province_map['province_name_mapped'] = province_map['province_name_normalized'].map(lambda x: manual_mapping.get(x, x))
    # STEP 1: Extended and normalized mapping dictionary
    manual_mapping2 = {
        # Persian → English
        "آذربايجان شرقي": "east azarbaijan",
        "آذربايجان غربي": "west azarbaijan",
        "اردبيل": "ardebil",
        "اصفهان": "esfahan",
        "البرز": "alborz",
        "ايلام": "ilam",
        "بوشهر": "bushehr",
        "تهران": "tehran",
        "چهارمحال و بختياري": "chahar mahall and bakhtiari",
        "خراسان جنوبي": "south khorasan",
        "خراسان رضوي": "razavi khorasan",
        "خراسان شمالي": "north khorasan",
        "خوزستان": "khuzestan",
        "زنجان": "zanjan",
        "سمنان": "semnan",
        "سيستان و بلوچستان": "sistan and baluchestan",
        "فارس": "fars",
        "قزوين": "qazvin",
        "قم": "qom",
        "كردستان": "kordestan",
        "كرمان": "kerman",
        "كرمانشاه": "kermanshah",
        "كهگيلويه و بويراحمد": "kohgiluyeh and buyer ahmad",
        "گلستان": "golestan",
        "گيلان": "gilan",
        "لرستان": "lorestan",
        "مازندران": "mazandaran",
        "مركزي": "markazi",
        "هرمزگان": "hormozgan",
        "همدان": "hamadan",
        "يزد": "yazd",

        # Also map lowercase English to normalized English (for consistency)
        "esfahan": "esfahan",
        "alborz": "alborz",
        "bushehr": "bushehr",
        "tehran": "tehran",
        "khuzestan": "khuzestan",
        "kermanshah": "kermanshah",
        "zanjan": "zanjan",
        "semnan": "semnan",
        "fars": "fars",
        "qom": "qom",
        "kermanshah": "kermanshah",
        "golestan": "golestan",
        "lorestan": "lorestan",
        "mazandaran": "mazandaran",
        "markazi": "markazi",
        "hormozgan": "hormozgan",
        "kordestan": "kordestan",
        "hamadan": "hamadan",
        "yazd": "yazd"
    }

    # STEP 2: Normalize the mapping dict (lowercase keys)
    manual_mapping_normalized = {k.strip().lower(): v for k, v in manual_mapping2.items()}

    # STEP 3: Normalize province names (input data)
    province_map['province_name_normalized'] = province_map['province_name_normalized'].str.strip().str.lower()

    # STEP 4: Apply the mapping
    province_map['province_name_mapped'] = province_map['province_name_normalized'].map(
        lambda x: manual_mapping_normalized.get(x, x)  # fallback to original if no match
    )



    # logger.info(province_map['province_name_mapped'])
    province_map_dict = dict(zip(province_map['province_name_mapped'], province_map['province_code']))
    province_name_dict = dict(zip(province_map['province_code'], province_map['province_name']))  # Persian names

    # Fetch faculty data by gender
    cursor = conn.cursor()
    cursor.execute("""
        SELECT faculty.province_code,
               CASE sex WHEN 1 THEN '1' WHEN 2 THEN '2' END AS sex,
               COUNT(*) AS cnt
        FROM faculty
        WHERE sex IN (1, 2)
        GROUP BY faculty.province_code, sex
        ORDER BY province_code desc
    """)
    rows = cursor.fetchall()
    conn.close()

    province_data = defaultdict(lambda: {'1': 0, '2': 0})
    for province_code, sex, count in rows:
        province_data[province_code][sex] = count

    # Create base map
    fig, ax = plt.subplots(figsize=(15, 26))
    iran_gdf.plot(ax=ax, color='#eee', edgecolor='#ccc')
    fig.subplots_adjust(top=1.37)
    plt.tight_layout(rect=[0, 0.15, 1, 0.1])

    for idx, row in iran_gdf.iterrows():
        province_name_en = row['NAME_1']
        province_name_norm = row['NAME_1_normalized'].lower()
        province_code = province_map_dict.get(province_name_norm, None)
        # logger.info(">>>>"+province_name_norm+"   "+str(province_code))
        values = [1, 1] if province_code is None else [
            int(province_data[province_code].get('1', 0)),
            int(province_data[province_code].get('2', 0))
        ]
        if sum(values) == 0:
            values = [1, 1]

        centroid = row['geometry'].centroid
        try:
            pie_ax = inset_axes(ax, width=0.65, height=1.65, loc='center',
                                bbox_to_anchor=(centroid.x, centroid.y),
                                bbox_transform=ax.transData,
                                borderpad=15)
            pie_ax.pie(values, labels=None, colors=['#36A2EB', '#FF6384'], explode=(0.1, 0), autopct='%1.0f%%', startangle=90)
            pie_ax.axis('equal')
        except Exception as e:
            logger.error(f"Error rendering pie chart for {province_name_en}: {e}")
            continue

    # Add legend and title
    male_patch = mpatches.Patch(color='#36A2EB', label=reshape_rtl("مرد"))
    female_patch = mpatches.Patch(color='#FF6384', label=reshape_rtl("زن"))
    ax.legend(handles=[male_patch, female_patch], loc='lower center', bbox_to_anchor=(0.5, -0.05), ncol=2)

    font_path = 'C:\\services\\cert2\\app\\static\\fonts\\Vazir.ttf'
    font_prop = font_manager.FontProperties(fname=font_path)
    today_shamsi = jdatetime.date.today().strftime('%Y/%m/%d')

    ax.set_title(reshape_rtl("توزیع اعضای هیات علمی به تفکیک جنسیت در هر استان"), fontproperties=font_prop, fontsize=24)
    ax.text(0.5, 0.97, reshape_rtl(f"تاریخ: {today_shamsi}"),
            transform=ax.transAxes, ha='center', fontsize=16, fontproperties=font_prop)
    ax.axis('off')

    # Generate table data
    # Step 1: Calculate the national total faculty count
    national_total = 0
    # logger.info(province_data.items())
    for code, data in province_data.items():
        male = int(data.get('1', 0))
        female = int(data.get('2', 0))
        national_total += male + female    
    
    # Step 2: Build the table including the new percentage column
    table_data = []
    row_number = 1
    total_male = 0
    total_female = 0
    total_sum = 0    
    # Reverse the mapping to get English → Persian
    reverse_manual_mapping = {v: k for k, v in manual_mapping.items()}

    # Collect all data into a list
    province_rows = []
    for idx, row in iran_gdf.iterrows():
        province_name_norm = row['NAME_1_normalized']
        province_name_fa = reverse_manual_mapping.get(province_name_norm, row['NAME_1'])

        province_rows.append({
            'idx': idx,
            'row': row,
            'province_name_fa': province_name_fa
        })

    # Custom sorting: move 'کهگیلویه و بویراحمد' to the top
    province_rows_sorted = sorted(
        province_rows,
        key=lambda x: (x['province_name_fa'])
    )

    # Final loop
    for item in province_rows_sorted:
        row = item['row']
        province_name_norm = row['NAME_1_normalized']
        province_name_fa = reshape_rtl(item['province_name_fa'])
            
        province_code = province_map_dict.get(province_name_norm, None)

        if province_code is None:
            male_count, female_count = 0, 0
        else:
            male_count = int(province_data[province_code].get('1', 0))
            total_male += male_count
            female_count = int(province_data[province_code].get('2', 0))

        total = male_count + female_count
        total_female += female_count
        total_sum += total
        male_percent = (male_count / total * 100) if total > 0 else 0
        female_percent = (female_count / total * 100) if total > 0 else 0
        national_percent = (total / national_total * 100) if national_total > 0 else 0

        table_data.append([
            f"{male_percent:1.0f}%",
            f"{female_percent:1.0f}%",
            f"{male_count:,}",
            f"{female_count:,}",
            f"{total:,}",
            f"{national_percent:.1f}%",  # <-- New column here
            province_name_fa,
            row_number,
        ])
        row_number += 1

    table_data.append([
        f"{100*total_male/total_sum:1.0f}%",
        f"{100*total_female/total_sum:1.0f}%",
        f"{total_male:,}",
        f"{total_female:,}",
        f"{total_sum:,}",
        "",  # <-- New column here
        reshape_rtl("جمع کل"),
        "",
    ])        
        
        
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

    # Create table area
    from matplotlib import gridspec
    spec = gridspec.GridSpec(nrows=2, ncols=1, height_ratios=[4, 1])
    ax_table = fig.add_subplot(spec[1])
    ax_table.axis('off')
    table = ax_table.table(
        cellText=table_data,
        cellLoc='center',
        loc='center',
        colWidths=[0.1, 0.1, 0.15, 0.15, 0.17, 0.15, 0.2, 0.06]
    )
    table.auto_set_font_size(False)
    table.set_fontsize(14)
    table.scale(1, 2)

    # Return image
    img = io.BytesIO()
    FigureCanvas(fig).print_png(img)
    img.seek(0)
    return send_file(img, mimetype='image/png')
