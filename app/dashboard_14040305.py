# dashboard.py

from flask import Blueprint, session, render_template, abort, redirect, url_for
from dashboards_config import DASHBOARDS
import logging
import sqlite3
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = "C:\\services\\cert2\\app\\access_control.db"

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboards")
def get_accessible_dashboards():
    access_levels = session.get("access_level", [])
    if isinstance(access_levels, str):
        access_levels = [access_levels]

    dashboards = set()
    print(f"Using DB path: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for level in access_levels:
        cursor.execute("""
            SELECT d.dashboard_id
            FROM dashboards d
            JOIN role_dashboard rd ON d.id = rd.dashboard_id
            JOIN roles r ON r.id = rd.role_id
            WHERE r.name = ?
        """, (level,))
        rows = cursor.fetchall()
        dashboards.update(row[0] for row in rows)

    conn.close()
    return dashboards

# def get_accessible_dashboards():
#     access_level = session.get("access_level", [])
#     dashboards = set()
#     for level in access_level:
#         dashboards.update(DASHBOARDS.get(level, []))
#         if "all_dashboards" in DASHBOARDS.get(level, []):
#             # Admin case: access to all dashboards
#             dashboards = get_all_dashboard_ids()
#             break
#     return dashboards

# def get_all_dashboard_ids():
#     # You can dynamically list templates or hardcode for now
#     return {
#         "sales_summary",
#         "team_performance",
#         "full_data_insights",
#         "etl_logs",
#         "model_metrics"
#     }

@dashboard_bp.route("/")
def dashboard_list():
    dashboards = get_accessible_dashboards()
    return render_template("dashboard_list.html", dashboards=dashboards)

@dashboard_bp.route("/<dashboard_id>")
def show_dashboard(dashboard_id):
    accessible_dashboards = get_accessible_dashboards()
    if dashboard_id not in accessible_dashboards:
        return render_template("error.html", error="Unauthorized access"), 403
    try:
        return render_template(f"dashboards/{dashboard_id}.html")
    except Exception as e:
        return render_template("error.html", error="Dashboard not found"), 404


@dashboard_bp.route('/dashboards/')
def dashboard_list():
    # ✅ Enforce authentication
    if 'userinfo' not in session:
        logging.info("User not authenticated, redirecting to login")
        return redirect(url_for('auth.login'))  # or whatever your login route is

    user_info = session['userinfo']
    level = user_info.get('usertype')

    dashboards = get_accessible_dashboards(level)
    return render_template('dashboard_list.html', dashboards=dashboards, user=user_info)