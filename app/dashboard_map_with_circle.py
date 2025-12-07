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
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
import io
import base64
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from flask import send_file

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
        # return render_template(f"dashboards/{dashboard_id}.html")
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
    import pandas as pd
    import matplotlib.pyplot as plt
    from shapely.geometry import Point
    import io
    from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
    from flask import send_file

    # Load shapefile
    iran_gdf = gpd.read_file("data/iran_shapefile/gadm41_IRN_1.shp")[['NAME_1', 'geometry']]
    iran_gdf['NAME_1'] = iran_gdf['NAME_1'].str.strip()

    # Load faculty data
    conn = sqlite3.connect("C:/services/cert2/app/fetch_data/faculty_data.db")
    df = pd.read_sql_query("""
        SELECT province_code, sex, COUNT(*) as count
        FROM faculty
        GROUP BY province_code, sex
    """, conn)

    province_map = pd.read_sql_query("SELECT province_code, province_name FROM province", conn)
    conn.close()

    df = df.merge(province_map, on='province_code')
    df_pivot = df.pivot(index='province_name', columns='sex', values='count').fillna(0).reset_index()

    iran_gdf = iran_gdf.merge(df_pivot, left_on='NAME_1', right_on='province_name', how='left')
    iran_gdf.fillna(0, inplace=True)

    # Plot base map
    fig, ax = plt.subplots(figsize=(15, 15))
    iran_gdf.plot(ax=ax, color='lightgrey', edgecolor='black')

    # Draw circles at centroids
    for idx, row in iran_gdf.iterrows():
        centroid = row['geometry'].centroid
        circle = plt.Circle((centroid.x, centroid.y), radius=0.25, color='red', fill=False, linewidth=2)
        ax.add_patch(circle)

    ax.set_title("Faculty Gender Distribution by Province", fontsize=18)
    ax.axis('off')

    # Save to buffer and serve as image
    canvas = FigureCanvas(fig)
    buf = io.BytesIO()
    canvas.print_png(buf)
    buf.seek(0)
    plt.close(fig)
    return send_file(buf, mimetype='image/png')
