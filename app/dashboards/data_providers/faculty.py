"""
Faculty Data Provider
Provides faculty-related data with context-aware filtering
"""
from typing import Dict, List, Optional, Any
from collections import defaultdict
from .base import DataProvider
from dashboards.config import DashboardConfig
from dashboards.context import UserContext

class FacultyDataProvider(DataProvider):
    """Data provider for faculty-related data"""
    
    def get_default_db_path(self) -> str:
        return DashboardConfig.FACULTY_DB
    
    def get_faculty_by_sex(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None) -> Dict[str, List]:
        """Get faculty statistics by gender"""
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters)
        
        query = f"""
            SELECT 
                CASE sex
                    WHEN 1 THEN 'مرد'
                    WHEN 2 THEN 'زن'
                    ELSE 'نامشخص'
                END AS sex_label,
                COUNT(*) as count
            FROM faculty
            {where_clause}
            GROUP BY sex
            ORDER BY count DESC
        """
        
        results = self.execute_query(query, tuple(params), context)
        return {
            "labels": [row[0] for row in results],
            "counts": [row[1] for row in results]
        }
    
    def get_faculty_by_markaz(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None) -> Dict[str, List]:
        """Get faculty by center with gender breakdown"""
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters)
        
        query = f"""
            SELECT 
                f.markaz,
                CASE f.sex
                    WHEN 1 THEN 'مرد'
                    WHEN 2 THEN 'زن'
                    ELSE 'نامشخص'
                END AS sex_label,
                COUNT(*) AS count
            FROM faculty f
            {where_clause}
            GROUP BY f.code_markaz, f.sex
            ORDER BY f.markaz
        """
        
        results = self.execute_query(query, tuple(params), context)
        
        # Process and group data
        grouped = {}
        for markaz, sex, count in results:
            markaz = markaz or "نامشخص"
            if markaz not in grouped:
                grouped[markaz] = {'مرد': 0, 'زن': 0, 'نامشخص': 0}
            grouped[markaz][sex] = count
        
        markaz_labels = list(grouped.keys())
        return {
            "labels": markaz_labels,
            "male_counts": [grouped[m]['مرد'] for m in markaz_labels],
            "female_counts": [grouped[m]['زن'] for m in markaz_labels]
        }
    
    def get_faculty_by_field(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None) -> Dict[str, List]:
        """Get faculty by field"""
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters)
        
        query = f"""
            SELECT field, COUNT(*) as count
            FROM faculty
            {where_clause}
            GROUP BY field
            ORDER BY count DESC
        """
        
        results = self.execute_query(query, tuple(params), context)
        return {
            "labels": [row[0] or "نامشخص" for row in results],
            "counts": [row[1] for row in results]
        }
    
    def get_faculty_by_type(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None) -> Dict[str, List]:
        """Get faculty by employment type"""
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters)
        
        query = f"""
            SELECT estekhdamtype_title, COUNT(*) as count
            FROM faculty
            {where_clause}
            GROUP BY estekhdamtype
            ORDER BY count DESC
        """
        
        results = self.execute_query(query, tuple(params), context)
        return {
            "labels": [row[0] or "نامشخص" for row in results],
            "counts": [row[1] for row in results]
        }
    
    def get_faculty_by_province(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None) -> Dict[str, Dict]:
        """Get faculty by province with gender breakdown"""
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters)
        
        query = f"""
            SELECT 
                province_code,
                CASE sex WHEN 1 THEN '1' WHEN 2 THEN '2' END AS sex,
                COUNT(*) AS count
            FROM faculty
            WHERE sex IN (1, 2)
            {where_clause}
            GROUP BY province_code, sex
        """
        
        results = self.execute_query(query, tuple(params), context)
        
        province_data = {}
        for province_code, sex, count in results:
            if province_code not in province_data:
                province_data[province_code] = {'1': 0, '2': 0}
            province_data[province_code][sex] = count
        
        return province_data
    
    def get_faculty_by_type_and_sex(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """Get faculty by employment type and sex (for nested pie chart)"""
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters)
        
        query = f"""
            SELECT estekhdamtype_title,
                CASE sex
                    WHEN 1 THEN 'مرد'
                    WHEN 2 THEN 'زن'
                    ELSE 'نامشخص'
                END AS sex_label,
                COUNT(*) AS count
            FROM faculty
            {where_clause}
            GROUP BY estekhdamtype_title, sex
            ORDER BY estekhdamtype_title, sex
        """
        
        results = self.execute_query(query, tuple(params), context)
        
        # Structure for nested pie chart
        grouped_data = defaultdict(lambda: defaultdict(int))
        
        for row in results:
            estekhdam = row[0] or "نامشخص"
            sex = row[1]
            count = row[2]
            grouped_data[estekhdam][sex] += count
        
        # Inner ring (employment types)
        inner_labels = []
        inner_data = []
        
        # Outer ring (sex breakdown)
        outer_labels = []
        outer_data = []
        
        for estekhdam_type, sexes in grouped_data.items():
            total = sum(sexes.values())
            inner_labels.append(estekhdam_type)
            inner_data.append(total)
            
            for sex_label, count in sexes.items():
                outer_labels.append(f"{estekhdam_type} - {sex_label}")
                outer_data.append(count)
        
        return {
            "inner_labels": inner_labels,
            "inner_data": inner_data,
            "outer_labels": outer_labels,
            "outer_data": outer_data
        }
    
    def get_faculty_by_edugroup(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None) -> Dict[str, List]:
        """Get faculty by education group"""
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters)
        
        query = f"""
            SELECT group_title, COUNT(*) as count
            FROM faculty 
            LEFT OUTER JOIN faculty_golestan ON (faculty.professorCode = faculty_golestan.professorCode)
            {where_clause}
            GROUP BY group_title
            ORDER BY count DESC
        """
        
        results = self.execute_query(query, tuple(params), context)
        return {
            "labels": [row[0] or "نامشخص" for row in results],
            "counts": [row[1] for row in results]
        }
    
    def get_faculty_by_grade(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None) -> Dict[str, List]:
        """Get faculty by grade"""
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters)
        
        query = f"""
            SELECT faculty_golestan.grade, COUNT(*) as count
            FROM faculty 
            LEFT OUTER JOIN faculty_golestan ON (faculty.professorCode = faculty_golestan.professorCode)
            {where_clause}
            GROUP BY faculty_golestan.grade
            ORDER BY count DESC
        """
        
        results = self.execute_query(query, tuple(params), context)
        return {
            "labels": [row[0] or "نامشخص" for row in results],
            "counts": [row[1] for row in results]
        }
    
    def get_faculty_by_certificate(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None) -> Dict[str, List]:
        """Get faculty by last certificate"""
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters)
        
        query = f"""
            SELECT faculty_golestan.last_certificate, COUNT(*) as count
            FROM faculty 
            LEFT OUTER JOIN faculty_golestan ON (faculty.professorCode = faculty_golestan.professorCode)
            {where_clause}
            GROUP BY faculty_golestan.last_certificate
            ORDER BY count DESC
        """
        
        results = self.execute_query(query, tuple(params), context)
        return {
            "labels": [row[0] or "نامشخص" for row in results],
            "counts": [row[1] for row in results]
        }
    
    def get_faculty_type_golestan(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None) -> Dict[str, List]:
        """Get faculty by Golestan employment type"""
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters)
        
        query = f"""
            SELECT faculty_golestan.estekhdamtype_golestan, COUNT(*) as count
            FROM faculty 
            LEFT OUTER JOIN faculty_golestan ON (faculty.professorCode = faculty_golestan.professorCode)
            {where_clause}
            GROUP BY faculty_golestan.estekhdamtype_golestan
            ORDER BY count DESC
        """
        
        results = self.execute_query(query, tuple(params), context)
        return {
            "labels": [row[0] or "نامشخص" for row in results],
            "counts": [row[1] for row in results]
        }


