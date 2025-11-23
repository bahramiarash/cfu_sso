"""
Students Data Provider
Provides student-related data with context-aware filtering
"""
from typing import Dict, List, Optional, Set, Any
from collections import defaultdict
import locale
import random
from .base import DataProvider
from dashboards.config import DashboardConfig
from dashboards.context import UserContext

# Persian sort order
persian_order = 'اآبپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی'
def persian_sort_key(word):
    word = word.strip()
    return [persian_order.index(ch) if ch in persian_order else ord(ch) for ch in word]

class StudentsDataProvider(DataProvider):
    """Data provider for student-related data"""
    
    def get_default_db_path(self) -> str:
        return DashboardConfig.FACULTY_DB
    
    def get_students_by_grade_and_year(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Get students grouped by grade and entrance year
        
        Returns:
            Dict with labels (years) and datasets (one per grade)
        """
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters, existing_where=False)
        
        # Build base WHERE conditions for students
        base_conditions = [
            "degsdate IS NOT NULL",
            "LENGTH(degsdate) >= 4",
            "studentnum IS NOT NULL",
            "LENGTH(studentnum) >= 4",
            "gradname IS NOT NULL"
        ]
        
        # Combine base conditions with filters
        all_conditions = base_conditions.copy()
        if where_clause:
            # Remove "WHERE " prefix if exists
            filter_conditions = where_clause.replace("WHERE ", "").strip()
            if filter_conditions:
                all_conditions.append(filter_conditions)
        
        students_where = "WHERE " + " AND ".join(all_conditions) if all_conditions else ""
        
        # Get all distinct grades
        query_grades = f"""
            SELECT DISTINCT gradname 
            FROM Students 
            {students_where}
        """
        grades = [row[0] for row in self.execute_query(query_grades, tuple(params), context)]
        
        # Get total faculty count for ratio calculation
        # Build faculty query with same filters
        faculty_where, faculty_params = self.build_where_clause(filters, existing_where=False)
        query_faculty = f"SELECT COUNT(*) FROM faculty{faculty_where}"
        total_faculty_result = self.execute_query(query_faculty, tuple(faculty_params), context)
        total_faculty = total_faculty_result[0][0] if total_faculty_result else 0
        
        # Get students per year per grade
        query = f"""
            SELECT SUBSTR(studentnum, 0, 4) AS entrance_year,
                   gradname,
                   COUNT(*) AS student_count
            FROM Students
            {students_where}
            GROUP BY entrance_year, gradname
            ORDER BY entrance_year
        """
        
        results = self.execute_query(query, tuple(params), context)
        
        # Structure: {grade: {year: count}}
        grade_data = {}
        all_years = set()
        
        for year, grade, count in results:
            if grade not in grade_data:
                grade_data[grade] = {}
            grade_data[grade][year] = count
            all_years.add(year)
        
        # Prepare chart data
        sorted_years = sorted(all_years)
        grade_datasets = []
        
        for grade in grades:
            if grade not in grade_data:
                continue
            
            ratios = []
            for year in sorted_years:
                count = grade_data[grade].get(year, 0)
                ratio = round(count / total_faculty, 2) if total_faculty else 0
                ratios.append(ratio)
            
            grade_datasets.append({
                'label': grade,
                'data': ratios,
            })
        
        return {
            "labels": sorted_years,
            "datasets": grade_datasets
        }
    
    def get_gender_data(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None, year_404: bool = False) -> Dict[str, Any]:
        """Get gender distribution data"""
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters, existing_where=False)
        
        conditions = []
        if where_clause:
            conditions.append(where_clause.replace("WHERE ", ""))
        if year_404:
            conditions.append("SUBSTR(studentnum, 1, 3) = '404'")
        
        if conditions:
            final_where = "WHERE " + " AND ".join(conditions)
        else:
            final_where = ""
        
        query = f"SELECT sex, COUNT(*) as count FROM Students {final_where} GROUP BY sex"
        results = self.execute_query(query, tuple(params), context)
        
        return {
            "labels": [row[0].strip() if row[0] else "نامشخص" for row in results],
            "counts": [row[1] for row in results]
        }
    
    def get_vazeiyat_data(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None, year_404: bool = False) -> Dict[str, Any]:
        """Get vazeiyat (status) distribution data"""
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters, existing_where=False)
        
        conditions = []
        if where_clause:
            conditions.append(where_clause.replace("WHERE ", ""))
        if year_404:
            conditions.append("SUBSTR(studentnum, 1, 3) = '404'")
        
        if conditions:
            final_where = "WHERE " + " AND ".join(conditions)
        else:
            final_where = ""
        
        query = f"SELECT vazeiyat, COUNT(*) FROM Students {final_where} GROUP BY vazeiyat ORDER BY COUNT(*) DESC"
        results = self.execute_query(query, tuple(params), context)
        
        return {
            "labels": [row[0] if row[0] else "نامشخص" for row in results],
            "counts": [row[1] for row in results]
        }
    
    def get_province_vazeiyat_data(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """Get province and vazeiyat distribution data"""
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters, existing_where=False)
        
        query = f"SELECT trim(province), vazeiyat, COUNT(*) FROM Students {where_clause} GROUP BY province, vazeiyat ORDER BY trim(province)"
        results = self.execute_query(query, tuple(params), context)
        
        province_vazeiyat = defaultdict(lambda: defaultdict(int))
        for province, vazeiyat, count in results:
            province_vazeiyat[province or "نامشخص"][vazeiyat or "نامشخص"] = count
        
        sorted_provinces = sorted(province_vazeiyat.keys(), key=persian_sort_key)
        vazeiyat_categories = sorted({v for p in province_vazeiyat.values() for v in p.keys()})
        
        datasets = []
        for vazeiyat in vazeiyat_categories:
            datasets.append({
                "label": vazeiyat,
                "data": [province_vazeiyat[prov].get(vazeiyat, 0) for prov in sorted_provinces],
                "backgroundColor": f"rgba({random.randint(50,200)}, {random.randint(80,200)}, {random.randint(150,255)}, 0.8)"
            })
        
        return {
            "labels": sorted_provinces,
            "datasets": datasets
        }
    
    def get_course_data_by_grade(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None, grade: Optional[int] = None) -> Dict[str, Any]:
        """Get course distribution data by grade"""
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters, existing_where=False)
        
        conditions = []
        if where_clause:
            conditions.append(where_clause.replace("WHERE ", ""))
        if grade:
            conditions.append(f"grade={grade}")
        
        if conditions:
            final_where = "WHERE " + " AND ".join(conditions)
        else:
            final_where = ""
        
        query = f"SELECT course_name, COUNT(*) as count FROM Students {final_where} GROUP BY course_name ORDER BY count DESC"
        results = self.execute_query(query, tuple(params), context)
        
        return {
            "labels": [row[0] for row in results],
            "counts": [row[1] for row in results]
        }
    
    def get_grade_data(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """Get grade distribution data"""
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters, existing_where=False)
        
        query = f"SELECT gradname, COUNT(*) as count FROM Students {where_clause} GROUP BY gradname"
        results = self.execute_query(query, tuple(params), context)
        
        return {
            "labels": [row[0] for row in results],
            "counts": [row[1] for row in results]
        }
    
    def get_province_data(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """Get province distribution data"""
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters, existing_where=False)
        
        query = f"SELECT province, COUNT(*) as count FROM Students {where_clause} GROUP BY province ORDER BY province"
        results = self.execute_query(query, tuple(params), context)
        
        return {
            "labels": [row[0] for row in results],
            "counts": [row[1] for row in results]
        }
    
    def get_province_year_data(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """Get province and year distribution data"""
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters, existing_where=False)
        
        query = f"""
            SELECT substr(term, 1, 3) AS year, province, COUNT(*) AS count
            FROM Students
            {where_clause}
            GROUP BY year, province
            ORDER BY province, year
        """
        results = self.execute_query(query, tuple(params), context)
        
        provinces = sorted(set(row[1] for row in results))
        years = sorted(set(row[0] for row in results))
        
        data_by_year = {year: [0] * len(provinces) for year in years}
        for row in results:
            province_idx = provinces.index(row[1])
            data_by_year[row[0]][province_idx] = row[2]
        
        return {
            "labels": provinces,
            "years": years,
            "data": data_by_year
        }
    
    def get_province_sex_data(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """Get province and sex distribution data"""
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters, existing_where=False)
        
        query = f"""
            SELECT sex, province, COUNT(*) AS count
            FROM Students
            {where_clause}
            GROUP BY sex, province
            ORDER BY province, sex
        """
        results = self.execute_query(query, tuple(params), context)
        
        provinces = sorted(set(row[1] for row in results))
        sex_list = sorted(set(row[0] for row in results))
        
        data_by_sex = {sex: [0] * len(provinces) for sex in sex_list}
        for row in results:
            province_idx = provinces.index(row[1])
            data_by_sex[row[0]][province_idx] = row[2]
        
        return {
            "labels": provinces,
            "sex_list": sex_list,
            "data": data_by_sex
        }
    
    def get_year_data(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """Get entry year distribution data by sex"""
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters, existing_where=False)
        
        query = f"""
            SELECT SUBSTR(studentnum, 1, 3) as prefix,
                   COUNT(*) as total,
                   SUM(CASE WHEN sex LIKE '%آقا%' THEN 1 ELSE 0 END) as male,
                   SUM(CASE WHEN sex LIKE '%خانم%' THEN 1 ELSE 0 END) as female
            FROM Students
            {where_clause}
            GROUP BY prefix
            ORDER BY prefix
        """
        results = self.execute_query(query, tuple(params), context)
        
        return {
            "labels": [str(1400 + int(row[0]) - 400) for row in results],
            "total": [row[1] for row in results],
            "male": [row[2] for row in results],
            "female": [row[3] for row in results]
        }
    
    def get_year_grade_data(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """Get entry year distribution data by grade"""
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters, existing_where=False)
        
        query = f"""
            SELECT SUBSTR(studentnum, 1, 3) as prefix,
                   SUM(CASE WHEN grade = 1 THEN 1 ELSE 0 END) as kardani,
                   SUM(CASE WHEN grade = 2 THEN 1 ELSE 0 END) as napeyvaste,
                   SUM(CASE WHEN grade = 3 THEN 1 ELSE 0 END) as peyvaste,
                   SUM(CASE WHEN grade = 4 THEN 1 ELSE 0 END) as arshad
            FROM Students
            {where_clause}
            GROUP BY prefix
            ORDER BY prefix
        """
        results = self.execute_query(query, tuple(params), context)
        
        return {
            "labels": [str(1400 + int(row[0]) - 400) for row in results],
            "kardani": [row[1] for row in results],
            "peyvaste": [row[2] for row in results],
            "napeyvaste": [row[3] for row in results],
            "arshad": [row[4] for row in results]
        }
    
    def get_course_year_data(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None, grade: Optional[int] = None) -> Dict[str, Any]:
        """Get course and year distribution data"""
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters, existing_where=False)
        
        # Add grade condition to where clause
        conditions = []
        if where_clause:
            conditions.append(where_clause.replace("WHERE ", ""))
        if grade:
            conditions.append(f"grade={grade}")
        
        if conditions:
            final_where = "WHERE " + " AND ".join(conditions)
        else:
            final_where = ""
        
        query = f"""
            SELECT SUBSTR(studentnum, 1, 3) as prefix, course_name, COUNT(*) as count
            FROM Students
            {final_where}
            GROUP BY prefix, course_name
            ORDER BY count
        """
        results = self.execute_query(query, tuple(params), context)
        
        course_years = {}
        all_years = set()
        
        for row in results:
            year = str(1400 + int(row[0]) - 400)
            course = row[1]
            count = row[2]
            all_years.add(year)
            course_years.setdefault(course, {})[year] = count
        
        sorted_years = sorted(all_years)
        
        return {
            "labels": sorted_years,
            "datasets": [
                {
                    "label": course,
                    "data": [course_years[course].get(year, 0) for year in sorted_years]
                } for course in course_years
            ]
        }

