# الگوی ایجاد داشبورد جدید

این سند الگوی کامل برای ایجاد یک داشبورد جدید را نشان می‌دهد.

## 📋 مراحل ایجاد داشبورد جدید

### مرحله 1: تعریف Data Provider (در صورت نیاز)

اگر داده‌های جدید نیاز دارید:

```python
# app/dashboards/data_providers/your_data.py
from .base import DataProvider
from dashboards.config import DashboardConfig

class YourDataProvider(DataProvider):
    def get_default_db_path(self) -> str:
        return DashboardConfig.YOUR_DB_PATH
    
    def get_your_data(self, **filters):
        """Get your specific data"""
        query = """
            SELECT column1, column2, COUNT(*) as count
            FROM your_table
            WHERE 1=1
        """
        # Add filters dynamically
        params = []
        if filters.get('date_from'):
            query += " AND date >= ?"
            params.append(filters['date_from'])
        
        return self.execute_query_dict(query, tuple(params))
```

### مرحله 2: ایجاد Dashboard Class

```python
# app/dashboards/dashboards/your_dashboard.py
from ..base import BaseDashboard
from ..data_providers.your_data import YourDataProvider
from ..registry import DashboardRegistry
from ..cache import cached
from flask import render_template, make_response

@DashboardRegistry.register
class YourDashboard(BaseDashboard):
    """Your dashboard description"""
    
    def __init__(self):
        super().__init__(
            dashboard_id="your_dashboard_id",  # e.g., "d9"
            title="عنوان داشبورد",
            description="توضیحات داشبورد"
        )
        self.data_provider = YourDataProvider()
        self.cache_ttl = 300  # Cache time in seconds
    
    @cached(ttl=300)
    def get_data(self, **kwargs):
        """Fetch and process data"""
        # Get filters from request
        filters = {
            'date_from': kwargs.get('date_from'),
            'date_to': kwargs.get('date_to'),
        }
        
        # Fetch data
        raw_data = self.data_provider.get_your_data(**filters)
        
        # Process data for visualization
        processed_data = self._process_data(raw_data)
        
        return processed_data
    
    def _process_data(self, raw_data):
        """Process raw data for charts"""
        # Your processing logic here
        return {
            "labels": [...],
            "datasets": [...],
            # ... other processed data
        }
    
    def render(self, data):
        """Render dashboard template"""
        response = make_response(
            render_template("dashboards/your_dashboard.html", **data)
        )
        return self.add_no_cache_headers(response)
```

### مرحله 3: ایجاد Template

```html
<!-- app/templates/dashboards/your_dashboard.html -->
{% extends "base.html" %}

{% block content %}
<div class="container-fluid">
    <h2>عنوان داشبورد</h2>
    
    <!-- Chart 1 -->
    <div class="row mb-4">
        <div class="col-md-12">
            <div class="card">
                <div class="card-header">
                    <h5>نمودار 1</h5>
                </div>
                <div class="card-body">
                    <canvas id="chart1"></canvas>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Chart 2 -->
    <div class="row">
        <div class="col-md-6">
            <div class="card">
                <div class="card-header">
                    <h5>نمودار 2</h5>
                </div>
                <div class="card-body">
                    <canvas id="chart2"></canvas>
                </div>
            </div>
        </div>
    </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
    // Chart 1
    const ctx1 = document.getElementById('chart1').getContext('2d');
    new Chart(ctx1, {
        type: 'line',
        data: {
            labels: {{ labels|tojson }},
            datasets: {{ datasets|tojson }}
        },
        options: {
            responsive: true,
            plugins: {
                legend: { position: 'top' }
            }
        }
    });
</script>
{% endblock %}
```

### مرحله 4: ثبت در دیتابیس (برای Access Control)

```python
# Script برای اضافه کردن داشبورد به دیتابیس
from app import app
from models import db
import sqlite3

def register_dashboard(dashboard_id, title, roles):
    """Register dashboard in database"""
    conn = sqlite3.connect("app/access_control.db")
    cursor = conn.cursor()
    
    # Insert dashboard
    cursor.execute(
        "INSERT OR IGNORE INTO dashboards (dashboard_id, dashboard_title) VALUES (?, ?)",
        (dashboard_id, title)
    )
    
    # Get dashboard ID
    cursor.execute("SELECT id FROM dashboards WHERE dashboard_id = ?", (dashboard_id,))
    dash_id = cursor.fetchone()[0]
    
    # Assign to roles
    for role in roles:
        cursor.execute("SELECT id FROM roles WHERE name = ?", (role,))
        role_result = cursor.fetchone()
        if role_result:
            role_id = role_result[0]
            cursor.execute(
                "INSERT OR IGNORE INTO role_dashboard (role_id, dashboard_id) VALUES (?, ?)",
                (role_id, dash_id)
            )
    
    conn.commit()
    conn.close()

# Usage
register_dashboard("d9", "داشبورد جدید", ["staff", "admin"])
```

---

## ✅ Checklist ایجاد داشبورد جدید

- [ ] Data Provider ایجاد شده (در صورت نیاز)
- [ ] Dashboard Class ایجاد شده
- [ ] Template HTML ایجاد شده
- [ ] Dashboard در Registry ثبت شده
- [ ] Dashboard در دیتابیس ثبت شده
- [ ] Access Control تنظیم شده
- [ ] تست شده و کار می‌کند
- [ ] مستندسازی انجام شده

---

## 🚀 مثال کامل: داشبورد ساده

```python
# app/dashboards/dashboards/simple_example.py
from ..base import BaseDashboard
from ..registry import DashboardRegistry
from flask import render_template, make_response

@DashboardRegistry.register
class SimpleExampleDashboard(BaseDashboard):
    """Simple example dashboard"""
    
    def __init__(self):
        super().__init__(
            dashboard_id="example",
            title="داشبورد نمونه",
            description="یک داشبورد ساده برای نمونه"
        )
    
    def get_data(self, **kwargs):
        """Simple data - no database needed"""
        return {
            "message": "سلام دنیا!",
            "numbers": [1, 2, 3, 4, 5],
            "labels": ["الف", "ب", "ج", "د", "ه"]
        }
    
    def render(self, data):
        """Render simple template"""
        response = make_response(
            render_template("dashboards/example.html", **data)
        )
        return self.add_no_cache_headers(response)
```

---

## 📝 نکات مهم

1. **همیشه از Registry استفاده کنید**: `@DashboardRegistry.register`
2. **Cache را فعال کنید**: برای query‌های سنگین از `@cached` استفاده کنید
3. **Error Handling**: از `handle_request()` استفاده کنید که error handling دارد
4. **No-Cache Headers**: از `add_no_cache_headers()` استفاده کنید
5. **Logging**: از `self.logger` برای logging استفاده کنید

---

## 🔄 Migration از کد قدیمی

برای migration داشبورد قدیمی:

1. منطق دریافت داده را به Data Provider منتقل کنید
2. منطق پردازش را در `get_data()` قرار دهید
3. منطق رندر را در `render()` قرار دهید
4. Template را به‌روزرسانی کنید
5. Route قدیمی را حذف کنید


