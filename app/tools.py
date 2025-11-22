from flask import Blueprint, session, render_template, abort, redirect, url_for, jsonify, request
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
bp = Blueprint('tools', __name__)

tools_bp = Blueprint("tools", __name__, url_prefix="/tools")

# def get_accessible_tools():
#     access_levels = session.get("access_level", [])
#     if isinstance(access_levels, str):
#         access_levels = [access_levels]

#     tools = []
#     conn = sqlite3.connect(DB_PATH)
#     cursor = conn.cursor()

#     for level in access_levels:
#         cursor.execute("""
#             SELECT d.tools_id, d.tools_title
#             FROM tools d
#             JOIN role_tools rd ON d.id = rd.tools_id
#             JOIN roles r ON r.id = rd.role_id
#             WHERE r.name = ?
#         """, (level,))
#         rows = cursor.fetchall()
#         for tools_id, tools_title in rows:
#             tools.append({
#                 "tools_id": tools_id,
#                 "tools_title": tools_title or tools_id.replace('_', ' ').title()
#             })

#     conn.close()
#     return tools

@tools_bp.route("/")
@requires_auth
def tools_list():
    # Enforce authentication
    if 'user_info' not in session:
        logging.info("User not authenticated, redirecting to login")
        return redirect(url_for('login'))

    user_info = session['user_info']
    level = user_info.get('usertype')

    # Store usertype in session as access_level
    session['access_level'] = [level] if isinstance(level, str) else level

#     tools = get_accessible_tools()
    response = make_response(render_template("tools.html", user=user_info))

    # Add no-cache headers
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response