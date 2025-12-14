"""
LMS Data Provider
Provides LMS monitoring data with context-aware filtering
"""
from typing import Dict, List, Optional, Any
from collections import defaultdict
from datetime import datetime
import requests
import logging
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
        from datetime import timedelta
        import pytz
        
        # Default: show maximum 1 year of data
        now = datetime.now()
        max_start_time = now - timedelta(days=365)
        max_start_time_str = max_start_time.strftime('%Y-%m-%d %H:%M:%S')
        
        # Build WHERE clause based on filters
        where_clauses = []
        params = []
        
        # Apply time filter - only one filter at a time
        if filters:
            time_range = filters.get('time_range')
            date_from = filters.get('date_from')
            date_to = filters.get('date_to')
            time_from = filters.get('time_from', '00:00')
            time_to = filters.get('time_to', '23:59')
            
            # Priority: custom date range > time_range
            if date_from and date_to:
                # Custom date range
                try:
                    import jdatetime
                    # Parse Persian calendar date (format: YYYY/MM/DD)
                    from_date_parts = list(map(int, date_from.split('/')))
                    to_date_parts = list(map(int, date_to.split('/')))
                    
                    # Parse time (format: HH:MM)
                    time_from_parts = list(map(int, time_from.split(':')))
                    time_to_parts = list(map(int, time_to.split(':')))
                    
                    # Create jdatetime objects
                    start_jd = jdatetime.datetime(
                        from_date_parts[0], from_date_parts[1], from_date_parts[2],
                        time_from_parts[0], time_from_parts[1]
                    )
                    end_jd = jdatetime.datetime(
                        to_date_parts[0], to_date_parts[1], to_date_parts[2],
                        time_to_parts[0], time_to_parts[1]
                    )
                    
                    # Convert to Gregorian datetime
                    start_time = start_jd.togregorian()
                    end_time = end_jd.togregorian()
                    
                    # Ensure we're working with Tehran timezone
                    tehran_tz = pytz.timezone('Asia/Tehran')
                    if start_time.tzinfo is None:
                        start_time = tehran_tz.localize(start_time)
                    if end_time.tzinfo is None:
                        end_time = tehran_tz.localize(end_time)
                    
                    # Convert to naive datetime for SQLite
                    start_time = start_time.replace(tzinfo=None)
                    end_time = end_time.replace(tzinfo=None)
                    
                    # Add 1 second to end_time to include the entire end day (23:59:59)
                    # This ensures we capture all data for the end date
                    end_time = end_time + timedelta(seconds=1)
                    
                    # Ensure not more than 1 year
                    if start_time < max_start_time:
                        start_time = max_start_time
                    
                    start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
                    end_time_str = end_time.strftime('%Y-%m-%d %H:%M:%S')
                    
                    # Use < instead of <= to include all data up to (but not including) end_time
                    # Since we added 1 second to end_time, this will include all data for the end date
                    where_clauses.append("datetime(timestamp) >= datetime(?) AND datetime(timestamp) < datetime(?)")
                    params.extend([start_time_str, end_time_str])
                except (ValueError, IndexError, AttributeError) as e:
                    # Invalid date, use default 1 year
                    where_clauses.append("datetime(timestamp) >= datetime(?)")
                    params.append(max_start_time_str)
            elif time_range:
                # Predefined time range
                if time_range == '1h':
                    start_time = now - timedelta(hours=1)
                elif time_range == '3h':
                    start_time = now - timedelta(hours=3)
                elif time_range == '6h':
                    start_time = now - timedelta(hours=6)
                elif time_range == '12h':
                    start_time = now - timedelta(hours=12)
                elif time_range == '1d':
                    start_time = now - timedelta(days=1)
                elif time_range == '1w':
                    start_time = now - timedelta(weeks=1)
                elif time_range == '1m':
                    start_time = now - timedelta(days=30)
                elif time_range == '1y':
                    start_time = now - timedelta(days=365)
                else:
                    start_time = max_start_time
                
                # Ensure not more than 1 year
                if start_time < max_start_time:
                    start_time = max_start_time
                
                start_time_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
                where_clauses.append("datetime(timestamp) >= datetime(?)")
                params.append(start_time_str)
            else:
                # No filter, use default 1 year
                where_clauses.append("datetime(timestamp) >= datetime(?)")
                params.append(max_start_time_str)
        else:
            # No filters, use default 1 year
            where_clauses.append("datetime(timestamp) >= datetime(?)")
            params.append(max_start_time_str)
        
        # Build query
        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
        # CRITICAL: Add LIMIT to prevent loading too much data at once
        # This improves performance significantly for large datasets
        # 50000 records should be enough for most time ranges
        query = f"""
            SELECT url, timestamp, key, value
            FROM monitor_data
            WHERE {where_clause}
            ORDER BY url, timestamp DESC
            LIMIT 50000
        """
        
        rows = self.execute_query(query, tuple(params), context)
        
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
        
        # Mapping from full URL to zone name
        url_to_zone = {
            "https://lms1.cfu.ac.ir/mod/adobeconnect/monitor.php": "Zone1",
            "https://lms2.cfu.ac.ir/mod/adobeconnect/monitor.php": "Zone2",
            "https://lms3.cfu.ac.ir/mod/adobeconnect/monitor.php": "Zone3",
            "https://lms4.cfu.ac.ir/mod/adobeconnect/monitor.php": "Zone4",
            "https://lms5.cfu.ac.ir/mod/adobeconnect/monitor.php": "Zone5",
            "https://lms6.cfu.ac.ir/mod/adobeconnect/monitor.php": "Zone6",
            "https://lms7.cfu.ac.ir/mod/adobeconnect/monitor.php": "Zone7",
            "https://lms8.cfu.ac.ir/mod/adobeconnect/monitor.php": "Zone8",
            "https://lms9.cfu.ac.ir/mod/adobeconnect/monitor.php": "Zone9",
            "https://lms10.cfu.ac.ir/mod/adobeconnect/monitor.php": "Zone10",
            "https://meeting.cfu.ac.ir/mod/adobeconnect/monitor.php": "Zone11"
        }
        
        # Initialize all zones with empty data
        for zone_name in DashboardConfig.ZONE_ORDER:
            latest_values[zone_name] = {}
            latest_zone_resources[zone_name] = {}
            charts[zone_name] = {
                "labels": [],
                "datasets": [],
                "title": DashboardConfig.ZONES.get(zone_name, zone_name)
            }
        
        if rows:
            # Group data by zone name (convert URL to zone name)
            url_data = {}
            for url, timestamp, key, value in rows:
                # Convert URL to zone name
                zone_name = url_to_zone.get(url, url)  # Use zone name if mapping exists, otherwise use URL as-is
                if zone_name not in url_data:
                    url_data[zone_name] = {}
                if key not in url_data[zone_name]:
                    url_data[zone_name][key] = {"timestamps": [], "values": []}
                
                # Convert to Jalali date string
                ts = timestamp
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts)
                jalali_ts = to_jalali(ts)
                
                url_data[zone_name][key]["timestamps"].append(jalali_ts)
                url_data[zone_name][key]["values"].append(value)
            
            # Build Chart.js structure for each zone
            # نمایش همه Zone1 تا Zone11 (11 منطقه) حتی اگر داده نداشته باشند
            for zone_name in DashboardConfig.ZONE_ORDER:
                datasets = []
                labels = []
                
                # Get zone resources from metrics service
                hostname = DashboardConfig.HOSTNAMES.get(zone_name)
                if hostname:
                    try:
                        response = requests.get(
                            DashboardConfig.METRICS_SERVICE_URL,
                            params={"host": hostname},
                            timeout=2  # Reduced timeout to fail faster if service is unavailable
                        )
                        if response.status_code == 200:
                            latest_zone_resources[zone_name] = response.json()
                    except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
                        # Silently continue if metrics service is unavailable
                        # This allows dashboard to render even if metrics service is down
                        logger = logging.getLogger(__name__)
                        logger.debug(f"Metrics service unavailable for {hostname}: {e}")
                        pass
                    except Exception as e:
                        # Log other errors but continue
                        logger = logging.getLogger(__name__)
                        logger.debug(f"Error fetching metrics for {hostname}: {e}")
                
                # Process data if available for this zone
                if zone_name in url_data:
                    keys = url_data[zone_name]
                    if keys:
                        first_key = next(iter(keys))
                        labels = keys[first_key]["timestamps"]
                        
                        for key, data in keys.items():
                            datasets.append({
                                "label": chartlabels.get(key, key),
                                "data": data["values"],
                                "borderColor": get_color_for_key(key),
                                "backgroundColor": get_color_for_key(key),
                                "fill": False
                            })
                            # Latest value = last entry
                            if data["values"]:
                                latest_val = data["values"][-1]
                                latest_values[zone_name][key] = latest_val
                                
                                # Update overall sum
                                overall_sum[key] = overall_sum.get(key, 0) + latest_val
                
                # Update chart for this zone (already initialized above)
                charts[zone_name]["labels"] = labels
                charts[zone_name]["datasets"] = datasets
        
        return {
            "charts": charts,
            "latest_values": latest_values,
            "latest_zone_resources": latest_zone_resources,
            "overall_sum": overall_sum,
            "chartlabels": chartlabels,
            "zones": DashboardConfig.ZONES,
            "zone_order": DashboardConfig.ZONE_ORDER
        }


