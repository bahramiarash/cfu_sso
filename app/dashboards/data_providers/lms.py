"""
LMS Data Provider
Provides LMS monitoring data with context-aware filtering
"""
from typing import Dict, List, Optional, Any
from collections import defaultdict
from datetime import datetime
import requests
from .base import DataProvider
from dashboards.config import DashboardConfig
from dashboards.context import UserContext
from dashboards.utils import to_jalali, get_color_for_key
import jdatetime

class LMSDataProvider(DataProvider):
    """Data provider for LMS monitoring data"""
    
    def get_default_db_path(self) -> str:
        return DashboardConfig.FACULTY_DB
    
    def get_lms_monitoring_data(self, context: Optional[UserContext] = None, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Get LMS monitoring data for all zones
        
        Returns:
            Dict with charts, latest_values, latest_zone_resources, overall_sum
        """
        # Get data from monitor_data table
        query = """
            SELECT url, timestamp, key, value
            FROM monitor_data
            ORDER BY url, timestamp ASC
        """
        rows = self.execute_query(query, (), context)
        
        charts = {}
        latest_values = {}
        latest_zone_resources = {}
        overall_sum = {}
        
        chartlabels = {
            "online_lms_user": "کاربران آنلاین LMS",
            "online_adobe_class": "کلاس های درحال ضبط Adobe",
            "online_adobe_user": "کاربران Adobe",
            "online_quizes": "آزمونهای درحال برگزاری",
            "online_users_in_quizes": "کاربران درحال برگزاری آزمون",
        }
        
        if rows:
            # Group data by URL and key
            url_data = {}
            for url, timestamp, key, value in rows:
                if url not in url_data:
                    url_data[url] = {}
                if key not in url_data[url]:
                    url_data[url][key] = {"timestamps": [], "values": []}
                
                # Convert to Jalali date string
                ts = timestamp
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts)
                jalali_ts = to_jalali(ts)
                
                url_data[url][key]["timestamps"].append(jalali_ts)
                url_data[url][key]["values"].append(value)
            
            # Build Chart.js structure for each URL
            for url, keys in url_data.items():
                datasets = []
                first_key = next(iter(keys))
                labels = keys[first_key]["timestamps"]
                latest_values[url] = {}
                latest_zone_resources[url] = {}
                
                # Get zone resources from metrics service
                hostname = DashboardConfig.HOSTNAMES.get(url)
                if hostname:
                    try:
                        response = requests.get(
                            DashboardConfig.METRICS_SERVICE_URL,
                            params={"host": hostname},
                            timeout=5
                        )
                        if response.status_code == 200:
                            latest_zone_resources[url] = response.json()
                    except Exception as e:
                        print(f"Error fetching metrics for {hostname}: {e}")
                
                for key, data in keys.items():
                    datasets.append({
                        "label": chartlabels.get(key, key),
                        "data": data["values"],
                        "borderColor": get_color_for_key(key),
                        "backgroundColor": get_color_for_key(key),
                        "fill": False
                    })
                    # Latest value = last entry
                    latest_val = data["values"][-1]
                    latest_values[url][key] = latest_val
                    
                    # Update overall sum
                    overall_sum[key] = overall_sum.get(key, 0) + latest_val
                
                charts[url] = {
                    "labels": labels,
                    "datasets": datasets,
                    "title": DashboardConfig.ZONES.get(url, url)
                }
        
        return {
            "charts": charts,
            "latest_values": latest_values,
            "latest_zone_resources": latest_zone_resources,
            "overall_sum": overall_sum,
            "chartlabels": chartlabels,
            "zones": DashboardConfig.ZONES
        }


