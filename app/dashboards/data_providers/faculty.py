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
    
    def get_faculty_by_province(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None) -> Dict[int, Dict[str, int]]:
        """Get faculty by province with gender breakdown"""
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters, existing_where=True)
        
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
            if province_code is None:
                continue  # Skip rows with NULL province_code
            if province_code not in province_data:
                province_data[province_code] = {'1': 0, '2': 0}
            if sex:  # Only add if sex is not None
                province_data[province_code][sex] = count
        
        self.logger.info(f"get_faculty_by_province: Found data for {len(province_data)} provinces")
        if province_data:
            sample_province = list(province_data.keys())[0]
            self.logger.info(f"Sample province {sample_province}: {province_data[sample_province]}")
        
        # Log Esfahan (province_code=4) data specifically
        esfahan_data = province_data.get(4, {})
        if esfahan_data:
            male = esfahan_data.get('1', 0)
            female = esfahan_data.get('2', 0)
            total = male + female
            self.logger.info(f"Esfahan (province_code=4) data: Male={male}, Female={female}, Total={total}")
            if total > 0:
                self.logger.info(f"Esfahan percentages: Male={(male/total*100):.1f}%, Female={(female/total*100):.1f}%")
        else:
            self.logger.warning("Esfahan (province_code=4) data not found in province_data!")
        
        return province_data
    
    def get_province_names(self, context: Optional[UserContext] = None) -> Dict[int, str]:
        """Get province names mapped by province_code"""
        query = "SELECT province_code, province_name FROM province ORDER BY province_name"
        results = self.execute_query(query, (), context)
        return {row[0]: row[1] for row in results if row[0] is not None}
    
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
        
        # Build WHERE clause - handle context filters that might be added by execute_query
        # We need to add conditions for NULL check, but execute_query might add WHERE clause
        # So we'll use a subquery or handle it differently
        
        # Start with base WHERE conditions
        base_conditions = ["faculty_golestan.group_title IS NOT NULL", "faculty_golestan.group_title != ''"]
        base_where = " AND ".join(base_conditions)
        
        # Combine with user filters
        if where_clause:
            # Remove WHERE keyword if present and combine
            if where_clause.strip().upper().startswith('WHERE'):
                where_clause = where_clause[5:].strip()
            combined_where = f"WHERE {where_clause} AND {base_where}"
        else:
            combined_where = f"WHERE {base_where}"
        
        query = f"""
            SELECT group_title, COUNT(*) as count
            FROM faculty 
            LEFT OUTER JOIN faculty_golestan ON (faculty.professorCode = faculty_golestan.professorCode)
            {combined_where}
            GROUP BY group_title
            HAVING COUNT(*) > 0 AND group_title IS NOT NULL
            ORDER BY count DESC
        """
        
        try:
            # Execute query directly without context to avoid double WHERE clause
            # We'll handle context filters manually if needed
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Apply context filters manually if needed
            if context:
                context_conditions = []
                context_params = list(params)
                
                if context.data_filters.get('province_code'):
                    context_conditions.append("faculty.province_code = ?")
                    context_params.append(context.data_filters['province_code'])
                
                if context.data_filters.get('faculty_code'):
                    context_conditions.append("faculty.code_markaz = ?")
                    context_params.append(context.data_filters['faculty_code'])
                
                if context_conditions:
                    # Add context conditions to WHERE clause
                    if 'WHERE' in combined_where.upper():
                        combined_where += " AND " + " AND ".join(context_conditions)
                    else:
                        combined_where = "WHERE " + " AND ".join(context_conditions)
                    params = tuple(context_params)
            
            # Rebuild query with context filters
            query = f"""
                SELECT group_title, COUNT(*) as count
                FROM faculty 
                LEFT OUTER JOIN faculty_golestan ON (faculty.professorCode = faculty_golestan.professorCode)
                {combined_where}
                GROUP BY group_title
                HAVING COUNT(*) > 0 AND group_title IS NOT NULL
                ORDER BY count DESC
            """
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            conn.close()
            
            # Filter out None and empty values
            labels = []
            counts = []
            for row in results:
                if row[0] and str(row[0]).strip():  # Check if label exists and is not empty
                    labels.append(str(row[0]).strip())
                    counts.append(row[1])
            
            self.logger.info(f"get_faculty_by_edugroup: Query returned {len(results)} rows, filtered to {len(labels)} groups")
            if len(labels) > 0:
                self.logger.info(f"Sample labels: {labels[:5]}")
            else:
                self.logger.warning(f"get_faculty_by_edugroup: No valid groups found. Query: {query}, Params: {params}")
            
            return {
                "labels": labels,
                "counts": counts
            }
        except Exception as e:
            self.logger.error(f"Error in get_faculty_by_edugroup: {e}", exc_info=True)
            if 'conn' in locals():
                conn.close()
            return {
                "labels": [],
                "counts": []
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


