# راهنمای Refactoring داشبوردها

این راهنما مراحل عملی refactoring داشبوردها را نشان می‌دهد.

## 🎯 اهداف Refactoring

1. کاهش کدهای تکراری
2. افزایش قابلیت توسعه‌پذیری
3. تسهیل ایجاد داشبوردهای جدید
4. بهبود Performance با Cache
5. بهبود Maintainability

---

## 📁 ساختار پیشنهادی

```
app/
├── dashboards/
│   ├── __init__.py
│   ├── base.py                    # Base Dashboard Class
│   ├── registry.py                # Dashboard Registry
│   ├── config.py                  # Configuration
│   ├── utils.py                   # Utility Functions
│   ├── cache.py                   # Caching System
│   ├── exceptions.py              # Custom Exceptions
│   ├── data_providers/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── faculty.py
│   │   ├── students.py
│   │   └── lms.py
│   ├── visualizations/
│   │   ├── __init__.py
│   │   ├── charts.py
│   │   ├── maps.py
│   │   └── tables.py
│   └── dashboards/
│       ├── __init__.py
│       ├── faculty_stats.py       # d1
│       ├── faculty_map.py         # d2
│       ├── pardis_map.py          # d3
│       ├── student_faculty_ratio.py # d7
│       └── lms_monitoring.py      # d8
├── dashboard_routes.py            # Route Registration
└── data/
    └── province_mappings.json     # Province Mappings
```

---

## 🔧 مراحل پیاده‌سازی

### مرحله 1: ایجاد ساختار پایه

#### 1.1. ایجاد Utility Functions

```python
# app/dashboards/utils.py
import hashlib
import arabic_reshaper
from bidi.algorithm import get_display
import jdatetime
from datetime import datetime
from typing import Optional

def get_color_for_key(key: str) -> str:
    """Generate consistent color hex code based on a key string."""
    h = hashlib.md5(key.encode()).hexdigest()
    return f"#{h[:6]}"

def reshape_rtl(text: str) -> str:
    """Reshape Persian text for RTL display."""
    if not text:
        return ""
    reshaped = arabic_reshaper.reshape(str(text))
    return get_display(reshaped)

def to_jalali(dt: datetime) -> str:
    """Convert datetime to Jalali string."""
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    jalali = jdatetime.datetime.fromgregorian(datetime=dt)
    return jalali.strftime("%Y/%m/%d %H:%M")

def format_number(num: int, decimals: int = 0) -> str:
    """Format number with thousand separators."""
    if decimals > 0:
        return f"{num:,.{decimals}f}"
    return f"{num:,}"

def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide two numbers, return default if denominator is zero."""
    if denominator == 0:
        return default
    return numerator / denominator
```

#### 1.2. ایجاد Configuration

```python
# app/dashboards/config.py
import os
from pathlib import Path
import json

class DashboardConfig:
    """Centralized configuration for dashboards"""
    
    BASE_DIR = Path(__file__).parent.parent
    
    # Database paths
    FACULTY_DB = os.getenv(
        "FACULTY_DB_PATH",
        str(BASE_DIR / "fetch_data" / "faculty_data.db")
    )
    ACCESS_CONTROL_DB = os.getenv(
        "ACCESS_CONTROL_DB_PATH",
        str(BASE_DIR / "access_control.db")
    )
    
    # Service URLs
    METRICS_SERVICE_URL = os.getenv(
        "METRICS_SERVICE_URL",
        "http://127.0.0.1:6000/metrics"
    )
    
    # Cache settings
    CACHE_ENABLED = os.getenv("DASHBOARD_CACHE_ENABLED", "true").lower() == "true"
    CACHE_TTL = int(os.getenv("DASHBOARD_CACHE_TTL", "300"))
    
    # Shapefile path
    IRAN_SHAPEFILE = BASE_DIR / "data" / "iran_shapefile" / "gadm41_IRN_1.shp"
    
    # Province mappings
    _province_mappings = None
    
    @classmethod
    def get_province_mappings(cls):
        """Load province mappings from JSON file"""
        if cls._province_mappings is None:
            mapping_file = cls.BASE_DIR / "data" / "province_mappings.json"
            if mapping_file.exists():
                with open(mapping_file, 'r', encoding='utf-8') as f:
                    cls._province_mappings = json.load(f)
            else:
                cls._province_mappings = cls._get_default_mappings()
        return cls._province_mappings
    
    @classmethod
    def _get_default_mappings(cls):
        """Default province mappings"""
        return {
            "آذربایجان شرقی": "east azarbaijan",
            "آذربایجان غربی": "west azarbaijan",
            # ... rest of mappings
        }
```

#### 1.3. ایجاد Base Dashboard Class

```python
# app/dashboards/base.py
from abc import ABC, abstractmethod
from flask import render_template, make_response
from functools import wraps
import logging
from typing import Dict, Any, Optional

class DashboardError(Exception):
    """Custom exception for dashboard errors"""
    pass

class BaseDashboard(ABC):
    """Base class for all dashboards"""
    
    def __init__(self, dashboard_id: str, title: str, description: Optional[str] = None):
        self.dashboard_id = dashboard_id
        self.title = title
        self.description = description
        self.logger = logging.getLogger(f"dashboard.{dashboard_id}")
        self.cache_enabled = True
        self.cache_ttl = 300
    
    @abstractmethod
    def get_data(self, **kwargs) -> Dict[str, Any]:
        """Fetch and process data for dashboard"""
        pass
    
    @abstractmethod
    def render(self, data: Dict[str, Any]):
        """Render dashboard template with data"""
        pass
    
    def handle_request(self, **kwargs):
        """Main request handler with error handling"""
        try:
            data = self.get_data(**kwargs)
            return self.render(data)
        except Exception as e:
            self.logger.error(f"Error in dashboard {self.dashboard_id}: {e}", exc_info=True)
            return self.render_error(str(e))
    
    def render_error(self, error_message: str):
        """Render error page"""
        return render_template("error.html", error=error_message), 500
    
    def get_cache_key(self, **kwargs) -> str:
        """Generate cache key for this dashboard"""
        import hashlib
        key_str = f"{self.dashboard_id}:{str(kwargs)}"
        return f"dashboard:{hashlib.md5(key_str.encode()).hexdigest()}"
    
    def add_no_cache_headers(self, response):
        """Add no-cache headers to response"""
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
```

#### 1.4. ایجاد Dashboard Registry

```python
# app/dashboards/registry.py
from typing import Dict, List, Optional
from .base import BaseDashboard

class DashboardRegistry:
    """Registry for managing all dashboards"""
    
    _dashboards: Dict[str, BaseDashboard] = {}
    
    @classmethod
    def register(cls, dashboard_class):
        """Register a dashboard class"""
        instance = dashboard_class()
        cls._dashboards[instance.dashboard_id] = instance
        return dashboard_class
    
    @classmethod
    def get(cls, dashboard_id: str) -> Optional[BaseDashboard]:
        """Get dashboard instance by ID"""
        return cls._dashboards.get(dashboard_id)
    
    @classmethod
    def list_all(cls) -> List[BaseDashboard]:
        """List all registered dashboards"""
        return list(cls._dashboards.values())
    
    @classmethod
    def get_ids(cls) -> List[str]:
        """Get all dashboard IDs"""
        return list(cls._dashboards.keys())
    
    @classmethod
    def exists(cls, dashboard_id: str) -> bool:
        """Check if dashboard exists"""
        return dashboard_id in cls._dashboards
```

---

### مرحله 2: ایجاد Data Providers

#### 2.1. Base Data Provider

```python
# app/dashboards/data_providers/base.py
from abc import ABC, abstractmethod
import sqlite3
from typing import Dict, List, Any, Optional
import logging
from dashboards.config import DashboardConfig

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
    
    def execute_query(self, query: str, params: tuple = ()) -> List[tuple]:
        """Execute SQL query and return results"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()
            return results
        finally:
            conn.close()
    
    def execute_query_dict(self, query: str, params: tuple = ()) -> List[Dict]:
        """Execute query and return results as list of dicts"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
```

#### 2.2. Faculty Data Provider

```python
# app/dashboards/data_providers/faculty.py
from .base import DataProvider
from dashboards.config import DashboardConfig
from typing import Dict, List

class FacultyDataProvider(DataProvider):
    """Data provider for faculty-related data"""
    
    def get_default_db_path(self) -> str:
        return DashboardConfig.FACULTY_DB
    
    def get_faculty_by_sex(self) -> Dict[str, List]:
        """Get faculty statistics by gender"""
        query = """
            SELECT 
                CASE sex
                    WHEN 1 THEN 'مرد'
                    WHEN 2 THEN 'زن'
                    ELSE 'نامشخص'
                END AS sex_label,
                COUNT(*) as count
            FROM faculty
            GROUP BY sex
            ORDER BY count DESC
        """
        results = self.execute_query(query)
        return {
            "labels": [row[0] for row in results],
            "counts": [row[1] for row in results]
        }
    
    def get_faculty_by_markaz(self) -> Dict[str, List]:
        """Get faculty by center with gender breakdown"""
        query = """
            SELECT 
                f.markaz,
                CASE f.sex
                    WHEN 1 THEN 'مرد'
                    WHEN 2 THEN 'زن'
                    ELSE 'نامشخص'
                END AS sex_label,
                COUNT(*) AS count
            FROM faculty f
            GROUP BY f.code_markaz, f.sex
            ORDER BY f.markaz
        """
        results = self.execute_query(query)
        # Process and group data
        grouped = {}
        for markaz, sex, count in results:
            if markaz not in grouped:
                grouped[markaz] = {'مرد': 0, 'زن': 0, 'نامشخص': 0}
            grouped[markaz][sex] = count
        
        markaz_labels = list(grouped.keys())
        return {
            "labels": markaz_labels,
            "male_counts": [grouped[m]['مرد'] for m in markaz_labels],
            "female_counts": [grouped[m]['زن'] for m in markaz_labels]
        }
    
    def get_faculty_by_field(self) -> Dict[str, List]:
        """Get faculty by field"""
        query = """
            SELECT field, COUNT(*) as count
            FROM faculty
            GROUP BY field
            ORDER BY count DESC
        """
        results = self.execute_query(query)
        return {
            "labels": [row[0] or "نامشخص" for row in results],
            "counts": [row[1] for row in results]
        }
    
    def get_faculty_by_type(self) -> Dict[str, List]:
        """Get faculty by employment type"""
        query = """
            SELECT estekhdamtype_title, COUNT(*) as count
            FROM faculty
            GROUP BY estekhdamtype
            ORDER BY count DESC
        """
        results = self.execute_query(query)
        return {
            "labels": [row[0] or "نامشخص" for row in results],
            "counts": [row[1] for row in results]
        }
    
    def get_faculty_by_province(self) -> Dict[str, Dict]:
        """Get faculty by province with gender breakdown"""
        query = """
            SELECT 
                province_code,
                CASE sex WHEN 1 THEN '1' WHEN 2 THEN '2' END AS sex,
                COUNT(*) AS count
            FROM faculty
            WHERE sex IN (1, 2)
            GROUP BY province_code, sex
        """
        results = self.execute_query(query)
        
        province_data = {}
        for province_code, sex, count in results:
            if province_code not in province_data:
                province_data[province_code] = {'1': 0, '2': 0}
            province_data[province_code][sex] = count
        
        return province_data
```

---

### مرحله 3: ایجاد Visualization Components

#### 3.1. Chart Builder

```python
# app/dashboards/visualizations/charts.py
from typing import List, Dict, Any, Optional
from dashboards.utils import get_color_for_key

class ChartBuilder:
    """Builder for Chart.js chart configurations"""
    
    @staticmethod
    def create_line_chart(
        labels: List[str],
        datasets: List[Dict],
        options: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Create line chart configuration"""
        default_options = {
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "legend": {"display": True, "position": "top"}
            },
            "scales": {
                "y": {"beginAtZero": True}
            }
        }
        if options:
            default_options.update(options)
        
        return {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": datasets
            },
            "options": default_options
        }
    
    @staticmethod
    def create_pie_chart(
        labels: List[str],
        data: List[float],
        colors: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create pie chart configuration"""
        if not colors:
            colors = [get_color_for_key(label) for label in labels]
        
        return {
            "type": "pie",
            "data": {
                "labels": labels,
                "datasets": [{
                    "data": data,
                    "backgroundColor": colors
                }]
            },
            "options": {
                "responsive": True,
                "plugins": {
                    "legend": {"position": "right"},
                    "datalabels": {
                        "color": "#fff",
                        "font": {"weight": "bold"}
                    }
                }
            }
        }
    
    @staticmethod
    def create_bar_chart(
        labels: List[str],
        datasets: List[Dict],
        options: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Create bar chart configuration"""
        default_options = {
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "legend": {"display": True}
            },
            "scales": {
                "y": {"beginAtZero": True}
            }
        }
        if options:
            default_options.update(options)
        
        return {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": datasets
            },
            "options": default_options
        }
```

---

### مرحله 4: مثال Refactored Dashboard

#### 4.1. Faculty Stats Dashboard (d1)

```python
# app/dashboards/dashboards/faculty_stats.py
from ..base import BaseDashboard
from ..data_providers.faculty import FacultyDataProvider
from ..registry import DashboardRegistry
from ..cache import cached
from flask import render_template, make_response

@DashboardRegistry.register
class FacultyStatsDashboard(BaseDashboard):
    """Dashboard for faculty statistics (d1)"""
    
    def __init__(self):
        super().__init__(
            dashboard_id="d1",
            title="آمار اعضای هیئت علمی",
            description="آمار تفصیلی اعضای هیئت علمی"
        )
        self.data_provider = FacultyDataProvider()
        self.cache_ttl = 600  # 10 minutes
    
    @cached(ttl=600)
    def get_data(self, **kwargs):
        """Fetch faculty statistics"""
        return {
            "sex_data": self.data_provider.get_faculty_by_sex(),
            "markaz_data": self.data_provider.get_faculty_by_markaz(),
            "field_data": self.data_provider.get_faculty_by_field(),
            "type_data": self.data_provider.get_faculty_by_type(),
            "edugroup_data": self.data_provider.get_faculty_by_edugroup(),
            "grade_data": self.data_provider.get_faculty_by_grade(),
            "certificate_data": self.data_provider.get_faculty_by_certificate(),
            "type_sex_data": self.data_provider.get_faculty_by_type_and_sex(),
        }
    
    def render(self, data):
        """Render dashboard template"""
        response = make_response(
            render_template("dashboards/faculty_stats.html", **data)
        )
        return self.add_no_cache_headers(response)
```

---

## 📝 Checklist برای Refactoring

### قبل از شروع:
- [ ] Backup از کد فعلی
- [ ] ایجاد branch جدید در git
- [ ] مستندسازی ساختار فعلی

### مرحله 1: Infrastructure
- [ ] ایجاد ساختار دایرکتوری
- [ ] پیاده‌سازی BaseDashboard
- [ ] پیاده‌سازی DashboardRegistry
- [ ] ایجاد DashboardConfig
- [ ] ایجاد Utility Functions
- [ ] تست Infrastructure

### مرحله 2: Data Providers
- [ ] ایجاد BaseDataProvider
- [ ] پیاده‌سازی FacultyDataProvider
- [ ] پیاده‌سازی StudentsDataProvider
- [ ] پیاده‌سازی LMSDataProvider
- [ ] تست Data Providers

### مرحله 3: Visualization
- [ ] ایجاد ChartBuilder
- [ ] ایجاد MapBuilder
- [ ] تست Visualization Components

### مرحله 4: Caching
- [ ] پیاده‌سازی DashboardCache
- [ ] اضافه کردن @cached decorator
- [ ] تست Caching

### مرحله 5: Migration
- [ ] Refactor d1
- [ ] Refactor d2
- [ ] Refactor d3
- [ ] Refactor d7
- [ ] Refactor d8
- [ ] تست تمام داشبوردها

### مرحله 6: Cleanup
- [ ] حذف کدهای قدیمی
- [ ] حذف فایل‌های backup
- [ ] به‌روزرسانی مستندات

---

## 🎓 Best Practices

### 1. Naming Conventions
- Dashboard IDs: `d1`, `d2`, `faculty_stats`, etc.
- Class names: `FacultyStatsDashboard`
- File names: `faculty_stats.py`

### 2. Error Handling
- همیشه از try-except استفاده کنید
- Log کردن خطاها
- نمایش پیام خطای مناسب به کاربر

### 3. Performance
- استفاده از Cache برای query‌های سنگین
- استفاده از Connection Pooling
- Lazy Loading برای داده‌های بزرگ

### 4. Code Organization
- هر داشبورد در فایل جداگانه
- Data Providers جدا از Dashboards
- Visualization Components قابل استفاده مجدد

### 5. Testing
- Unit Tests برای Data Providers
- Integration Tests برای Dashboards
- Performance Tests

---

## 📚 منابع و مراجع

- Flask Blueprint Documentation
- SQLAlchemy Best Practices
- Design Patterns (Factory, Registry, Builder)
- Python ABC (Abstract Base Classes)


