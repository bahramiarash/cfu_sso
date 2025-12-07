"""
Base Data Provider
All data providers should inherit from this class
"""
from abc import ABC, abstractmethod
import sqlite3
from typing import Dict, List, Any, Optional
import logging
from dashboards.config import DashboardConfig
from dashboards.context import UserContext

logger = logging.getLogger(__name__)


class DataProvider(ABC):
    """Base class for data providers"""
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or self.get_default_db_path()
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def get_default_db_path(self) -> str:
        """Get default database path"""
        pass
    
    def get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    def execute_query(self, query: str, params: tuple = (), context: Optional[UserContext] = None) -> List[tuple]:
        """
        Execute SQL query and return results
        Automatically applies filters from context if provided
        
        Args:
            query: SQL query string
            params: Query parameters
            context: UserContext for applying access filters
        
        Returns:
            List of tuples (rows)
        """
        # Apply context filters to query if needed
        if context:
            query, params = self._apply_context_filters(query, params, context)
        
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()
            return results
        finally:
            conn.close()
    
    def execute_query_dict(self, query: str, params: tuple = (), context: Optional[UserContext] = None) -> List[Dict]:
        """
        Execute query and return results as list of dicts
        Automatically applies filters from context if provided
        
        Args:
            query: SQL query string
            params: Query parameters
            context: UserContext for applying access filters
        
        Returns:
            List of dictionaries (rows)
        """
        # Apply context filters to query if needed
        if context:
            query, params = self._apply_context_filters(query, params, context)
        
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
    
    def _apply_context_filters(self, query: str, params: tuple, context: UserContext) -> tuple:
        """
        Apply user context filters to SQL query
        Override in subclasses for custom filtering logic
        
        Args:
            query: Original SQL query
            params: Original query parameters
            context: UserContext with access filters
        
        Returns:
            Tuple of (modified_query, modified_params)
        """
        # Default implementation: add WHERE clause if needed
        filters = []
        new_params = list(params)
        
        # Add province filter if user is restricted to a province
        if context.data_filters.get('province_code'):
            if 'WHERE' not in query.upper():
                query += " WHERE "
            else:
                query += " AND "
            query += "province_code = ?"
            new_params.append(context.data_filters['province_code'])
        
        # Add faculty filter if user is restricted to a faculty
        if context.data_filters.get('faculty_code'):
            if 'WHERE' not in query.upper():
                query += " WHERE "
            else:
                query += " AND "
            # Try common faculty code column names
            if 'code_markaz' in query.lower():
                query += "code_markaz = ?"
            elif 'faculty_code' in query.lower():
                query += "faculty_code = ?"
            else:
                query += "code_markaz = ?"
            new_params.append(context.data_filters['faculty_code'])
        
        return query, tuple(new_params)
    
    def build_where_clause(self, filters: Dict[str, Any], existing_where: bool = False) -> tuple:
        """
        Build WHERE clause from filters dictionary
        
        Args:
            filters: Dictionary of filter conditions
            existing_where: Whether WHERE clause already exists in query
        
        Returns:
            Tuple of (where_clause_string, params_list)
        """
        conditions = []
        params = []
        
        # Support both single province_code and list of province_codes
        if filters.get('province_code'):
            conditions.append("province_code = ?")
            params.append(filters['province_code'])
        elif filters.get('province_codes'):
            # Support list of province codes (from filter_restrictions)
            province_codes = filters['province_codes']
            if isinstance(province_codes, list) and len(province_codes) > 0:
                placeholders = ','.join(['?' for _ in province_codes])
                conditions.append(f"province_code IN ({placeholders})")
                params.extend(province_codes)
        
        # Support both single university_code and list of university_codes
        if filters.get('university_code'):
            conditions.append("university_code = ?")
            params.append(filters['university_code'])
        elif filters.get('university_codes'):
            university_codes = filters['university_codes']
            if isinstance(university_codes, list) and len(university_codes) > 0:
                placeholders = ','.join(['?' for _ in university_codes])
                conditions.append(f"university_code IN ({placeholders})")
                params.extend(university_codes)
        
        # Support both single faculty_code and list of faculty_codes
        if filters.get('faculty_code'):
            # Try multiple column names
            conditions.append("(code_markaz = ? OR faculty_code = ?)")
            params.extend([filters['faculty_code'], filters['faculty_code']])
        elif filters.get('faculty_codes'):
            faculty_codes = filters['faculty_codes']
            if isinstance(faculty_codes, list) and len(faculty_codes) > 0:
                placeholders = ','.join(['?' for _ in faculty_codes])
                conditions.append(f"(code_markaz IN ({placeholders}) OR faculty_code IN ({placeholders}))")
                params.extend(faculty_codes)
                params.extend(faculty_codes)  # Add twice for both OR conditions
        
        if filters.get('date_from'):
            conditions.append("date >= ?")
            params.append(filters['date_from'])
        
        if filters.get('date_to'):
            conditions.append("date <= ?")
            params.append(filters['date_to'])
        
        if not conditions:
            return "", []
        
        where_clause = " AND ".join(conditions)
        if existing_where:
            where_clause = " AND " + where_clause
        else:
            where_clause = " WHERE " + where_clause
        
        return where_clause, params


