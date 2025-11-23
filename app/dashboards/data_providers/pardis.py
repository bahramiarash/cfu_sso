"""
Pardis Data Provider
Provides pardis-related data with context-aware filtering
"""
from typing import Dict, List, Optional
from collections import defaultdict
from .base import DataProvider
from dashboards.config import DashboardConfig
from dashboards.context import UserContext

class PardisDataProvider(DataProvider):
    """Data provider for pardis-related data"""
    
    def get_default_db_path(self) -> str:
        return DashboardConfig.ACCESS_CONTROL_DB
    
    def get_pardis_by_province(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None) -> Dict[int, Dict[int, int]]:
        """
        Get pardis distribution by province and type
        
        Returns:
            Dict mapping province_code to type counts
            e.g., {1: {1: 5, 2: 3, 3: 2}}  # province 1 has 5 pardis, 3 markaz, 2 daneshkade
        """
        filters = filters or {}
        where_clause, params = self.build_where_clause(filters)
        
        query = f"""
            SELECT province_code, type, COUNT(*) as cnt
            FROM pardis
            {where_clause}
            GROUP BY province_code, type
        """
        
        results = self.execute_query(query, tuple(params), context)
        
        province_data = defaultdict(lambda: {1: 0, 2: 0, 3: 0, 4: 0})
        for province_code, type_id, count in results:
            province_data[province_code][type_id] = count
        
        return dict(province_data)


