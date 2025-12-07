"""
API endpoints for dashboard filters
Provides data for filter dropdowns
"""
from flask import Blueprint, jsonify, request, session
from flask_login import login_required, current_user
from dashboards.context import get_user_context
from dashboards.data_providers.faculty import FacultyDataProvider
import sqlite3
import logging
from dashboards.config import DashboardConfig

logger = logging.getLogger(__name__)

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
        
        # Support province_code from query parameter (for admin panel)
        province_code = request.args.get('province_code')
        if province_code:
            try:
                province_code = int(province_code)
                query += " AND province_code = ?"
                params.append(province_code)
            except (ValueError, TypeError):
                pass
        elif context.province_code:
            query += " AND province_code = ?"
            params.append(context.province_code)
        
        # Support university_code from query parameter (for admin panel)
        university_code = request.args.get('university_code')
        if university_code:
            try:
                # Support comma-separated list
                university_codes = [int(c.strip()) for c in str(university_code).split(',') if c.strip()]
                if university_codes:
                    placeholders = ','.join(['?'] * len(university_codes))
                    query += f" AND university_code IN ({placeholders})"
                    params.extend(university_codes)
            except (ValueError, TypeError):
                pass
        elif context.university_code:
            query += " AND university_code = ?"
            params.append(context.university_code)
        
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
        logger.error(f"Error fetching faculties: {e}", exc_info=True)
        return jsonify({"error": str(e), "faculties": []}), 500

@api_bp.route('/universities')
@login_required
def get_universities():
    """Get list of universities user can access"""
    try:
        context = get_user_context()
        
        conn = sqlite3.connect(DashboardConfig.FACULTY_DB)
        cursor = conn.cursor()
        
        # Support province_code from query parameter (for admin panel)
        province_code = request.args.get('province_code')
        
        # First check if university table exists and has the right columns
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='university'
        """)
        university_table_exists = cursor.fetchone()
        
        # Check if faculty table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='faculty'
        """)
        faculty_table_exists = cursor.fetchone()
        
        universities = []
        
        if university_table_exists:
            # Try to get column names from university table
            cursor.execute("PRAGMA table_info(university)")
            columns = [col[1] for col in cursor.fetchall()]
            
            # Check if required columns exist
            if 'university_code' in columns and 'university_name' in columns:
                # Table exists with correct columns, use it
                query = """
                    SELECT DISTINCT university_code, university_name 
                    FROM university 
                    WHERE university_code IS NOT NULL
                """
                params = []
                
                if province_code:
                    try:
                        province_code = int(province_code)
                        if 'province_code' in columns:
                            query += " AND province_code = ?"
                            params.append(province_code)
                    except (ValueError, TypeError):
                        pass
                elif context.province_code and 'province_code' in columns:
                    query += " AND province_code = ?"
                    params.append(context.province_code)
                
                if context.university_code:
                    query += " AND university_code = ?"
                    params.append(context.university_code)
                
                query += " ORDER BY university_name"
                
                try:
                    cursor.execute(query, tuple(params))
                    universities = [{"code": row[0], "name": row[1]} for row in cursor.fetchall()]
                except Exception as e:
                    logger.warning(f"Error querying university table: {e}")
                    universities = []
        
        # If university table doesn't exist or query failed, try faculty table
        if not universities and faculty_table_exists:
            # Try to get column names from faculty table
            cursor.execute("PRAGMA table_info(faculty)")
            columns = [col[1] for col in cursor.fetchall()]
            
            # Check if required columns exist
            if 'university_code' in columns and 'university_name' in columns:
                query = """
                    SELECT DISTINCT university_code, university_name 
                    FROM faculty 
                    WHERE university_code IS NOT NULL
                """
                params = []
                
                if province_code:
                    try:
                        province_code = int(province_code)
                        if 'province_code' in columns:
                            query += " AND province_code = ?"
                            params.append(province_code)
                    except (ValueError, TypeError):
                        pass
                elif context.province_code and 'province_code' in columns:
                    query += " AND province_code = ?"
                    params.append(context.province_code)
                
                if context.university_code:
                    query += " AND university_code = ?"
                    params.append(context.university_code)
                
                query += " ORDER BY university_name"
                
                try:
                    cursor.execute(query, tuple(params))
                    universities = [{"code": row[0], "name": row[1]} for row in cursor.fetchall()]
                except Exception as e:
                    logger.warning(f"Error querying faculty table: {e}")
                    universities = []
        
        conn.close()
        
        return jsonify({"universities": universities})
    except Exception as e:
        logger.error(f"Error fetching universities: {e}", exc_info=True)
        return jsonify({"error": str(e), "universities": []}), 500


