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
    sex_labels = [row[0] for row in sex_data]
    sex_counts = [row[1] for row in sex_data]

    # First chart: Group by Markaz
    cursor.execute("""
    SELECT 
        scope || ' --- ' || f.markaz,
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

    grouped_data = defaultdict(lambda: {'زن': 0, 'مرد': 0, 'نامشخص': 0})

    for markaz, sex_label, count, _ in rows:
        markaz = markaz or "نامشخص"
        grouped_data[markaz][sex_label] += count

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

    grouped_data = defaultdict(lambda: defaultdict(int))

    for row in rows:
        estekhdam = row[0] or "نامشخص"
        sex = row[1]
        count = row[2]
        grouped_data[estekhdam][sex] += count

    inner_labels = []
    inner_data = []
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
                            inner_labels=inner_labels,
                            inner_data=inner_data,
                            outer_labels=outer_labels,
                            outer_data=outer_data))

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

    # Load shapefile
    iran_gdf = gpd.read_file("data/iran_shapefile/gadm41_IRN_1.shp")[['NAME_1', 'geometry']]
    iran_gdf['NAME_1'] = iran_gdf['NAME_1'].str.strip()

    # Connect to database
    DB_PATH2 = "C:\\services\\cert2\\app\\fetch_data\\faculty_data.db"
    conn = sqlite3.connect(DB_PATH2)

    # Fetch province mapping
    province_map = pd.read_sql_query("SELECT province_code, province_name FROM province", conn)
    # Normalize province names for better matching
    province_map['province_name_normalized'] = province_map['province_name'].str.strip().str.lower()
    iran_gdf['NAME_1_normalized'] = iran_gdf['NAME_1'].str.strip().str.lower()

    # Manual mapping for Persian to English names (based on observed discrepancies)
    manual_mapping = {
        'تهران': 'tehran',
        'خراسان رضوی': 'khorasan razavi',
        'اصفهان': 'esfahan',
        'فارس': 'fars',
        'خوزستان': 'khuzestan',
        'آذربایجان شرقی': 'east azarbaijan',
        'آذربایحان غربی': 'west azarbaijan',
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
        'چهارمحال و بختیاری': 'chahar mahaal and bakhtiari',
        'کردستان': 'kurdistan',
        'گلستان': 'golestan',
        'زنجان': 'zanjan',
        'سمنان': 'semnan',
        'قزوین': 'qazvin',
        'اردبیل': 'ardabil',
        'بوشهر': 'bushehr',
        'کهگیلویه و بویراحمد': 'kohgiluyeh and boyer ahmad',
        'ایلام': 'ilam',
        'خراسان شمالی': 'north khorasan',
        'خراسان جنوبی': 'south khorasan'
    }
    province_map['province_name_mapped'] = province_map['province_name_normalized'].map(lambda x: manual_mapping.get(x, x))
    province_map_dict = dict(zip(province_map['province_name_mapped'], province_map['province_code']))

    # Log the province names for debugging
    logger.info(f"Shapefile province names (normalized): {list(iran_gdf['NAME_1_normalized'])}")
    logger.info(f"Database province names (normalized): {list(province_map['province_name_normalized'])}")
    logger.info(f"Database province names (original): {list(province_map['province_name'])}")

    # Fetch gender distribution data
    cursor = conn.cursor()
    cursor.execute("""
        SELECT province_code,
               CASE sex WHEN 1 THEN '1' WHEN 2 THEN '2' END AS sex,
               COUNT(*) AS cnt
        FROM   faculty
        WHERE  sex IN (1, 2)
        GROUP  BY province_code, sex
    """)
    rows = cursor.fetchall()
    conn.close()

    # Log the query results for debugging
    logger.info(f"Query results: {rows}")

    # Aggregate data by province
    province_data = defaultdict(lambda: {'1': 0, '2': 0})
    for province_code, sex, count in rows:
        province_data[province_code][sex] = count

    # Plot base map
    fig, ax = plt.subplots(figsize=(15, 15))
    iran_gdf.plot(ax=ax, color='#eee', edgecolor='black')

    # Add pie charts at centroids of each province
    for idx, row in iran_gdf.iterrows():
        province_name = row['NAME_1']
        province_name_normalized = row['NAME_1_normalized']
        # Map province_name to province_code using the province_map_dict
        province_code = province_map_dict.get(province_name_normalized, None)
        if province_code is None:
            logger.warning(f"No province code found for {province_name} (normalized: {province_name_normalized})")
            # Render a default pie chart for debugging
            values = [1, 1]  # Default values to show a pie chart
        else:
            # Get values for this province and convert them to int
            values = [
                int(province_data[province_code].get('1', 0)),
                int(province_data[province_code].get('2', 0))
            ]
            if sum(values) == 0:
                logger.info(f"No data for {province_name} (Province Code: {province_code}, Values: {values})")
                values = [1, 1]  # Default values for provinces with no data

        logger.info(f"Rendering pie chart for {province_name} (Province Code: {province_code}, Values: {values})")

        colors = ['#36A2EB', '#FF6384']  # Blue for male, red for female
        explode = (0.1, 0)  # Slightly separate the male slice

        centroid = row['geometry'].centroid
        try:
            pie_ax = inset_axes(ax, width=0.85, height=0.75, loc='center',
                               bbox_to_anchor=(centroid.x, centroid.y),
                               bbox_transform=ax.transData,
                               borderpad=5)
            pie_ax.pie(values, labels=None, colors=colors, explode=explode, autopct='%1.0f%%', startangle=90)
            pie_ax.axis('equal')  # Ensure pie is circular
            pie_ax.set_title('')  # No title for individual pies
        except Exception as e:
            logger.error(f"Error rendering pie chart for {province_name}: {e}")
            continue

    # Add a color legend at the bottom of the map
    male_patch = mpatches.Patch(color='#36A2EB', label=reshape_rtl("مرد"))
    female_patch = mpatches.Patch(color='#FF6384', label=reshape_rtl("زن"))
    ax.legend(handles=[male_patch, female_patch], loc='lower center', bbox_to_anchor=(0.5, -0.05), ncol=2)
    font_path = 'C:\\services\\cert2\\app\\static\\fonts\\Vazir.ttf'
    font_prop = font_manager.FontProperties(fname=font_path)

    ax.set_title(
        reshape_rtl("توزیع اعضای هیات علمی به تفکیک جنسیت در هر استان"),
        fontproperties=font_prop,
        fontsize=24
    )
    ax.set_xticklabels([reshape_rtl(name) for name in province_name])
    ax.axis('off')

    # Save to buffer and serve as image
    canvas = FigureCanvas(fig)
    buf = io.BytesIO()
    canvas.print_png(buf)
    buf.seek(0)
    image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    image_uri = f"data:image/png;base64,{image_base64}"
    plt.close(fig)
    return send_file(buf, mimetype='image/png')