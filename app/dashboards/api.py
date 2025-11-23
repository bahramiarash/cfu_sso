"""
API endpoints for dashboard filters
Provides data for filter dropdowns
"""
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from dashboards.context import get_user_context
from dashboards.data_providers.faculty import FacultyDataProvider
import sqlite3
from dashboards.config import DashboardConfig

api_bp = Blueprint('dashboard_api', __name__, url_prefix='/api/dashboards')

@api_bp.route('/provinces')
@login_required
def get_provinces():
    """Get list of provinces user can access"""
    try:
        context = get_user_context()
        
        conn = sqlite3.connect(DashboardConfig.FACULTY_DB)
        cursor = conn.cursor()
        
        query = "SELECT province_code, province_name FROM province ORDER BY province_name"
        if context.province_code:
            # User can only see their province
            query += " WHERE province_code = ?"
            cursor.execute(query, (context.province_code,))
        else:
            cursor.execute(query)
        
        provinces = [{"code": row[0], "name": row[1]} for row in cursor.fetchall()]
        conn.close()
        
        return jsonify({"provinces": provinces})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route('/faculties')
@login_required
def get_faculties():
    """Get list of faculties user can access"""
    try:
        context = get_user_context()
        
        conn = sqlite3.connect(DashboardConfig.FACULTY_DB)
        cursor = conn.cursor()
        
        query = """
            SELECT DISTINCT code_markaz, markaz 
            FROM faculty 
            WHERE code_markaz IS NOT NULL
        """
        params = []
        
        if context.province_code:
            query += " AND province_code = ?"
            params.append(context.province_code)
        
        if context.faculty_code:
            # User can only see their faculty
            query += " AND code_markaz = ?"
            params.append(context.faculty_code)
        
        query += " ORDER BY markaz"
        
        cursor.execute(query, tuple(params))
        faculties = [{"code": row[0], "name": row[1]} for row in cursor.fetchall()]
        conn.close()
        
        return jsonify({"faculties": faculties})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route('/universities')
@login_required
def get_universities():
    """Get list of universities user can access"""
    try:
        context = get_user_context()
        
        conn = sqlite3.connect(DashboardConfig.FACULTY_DB)
        cursor = conn.cursor()
        
        query = """
            SELECT DISTINCT university_code, university_name 
            FROM university 
            WHERE university_code IS NOT NULL
        """
        params = []
        
        if context.province_code:
            query += " AND province_code = ?"
            params.append(context.province_code)
        
        if context.university_code:
            # User can only see their university
            query += " AND university_code = ?"
            params.append(context.university_code)
        
        query += " ORDER BY university_name"
        
        cursor.execute(query, tuple(params))
        universities = [{"code": row[0], "name": row[1]} for row in cursor.fetchall()]
        conn.close()
        
        return jsonify({"universities": universities})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


