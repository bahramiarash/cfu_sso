# وضعیت پیاده‌سازی سیستم داشبوردها

## ✅ کارهای انجام شده

### 1. Infrastructure (100%)
- ✅ ساختار دایرکتوری ایجاد شد
- ✅ BaseDashboard با پشتیبانی از UserContext
- ✅ DashboardRegistry برای مدیریت داشبوردها
- ✅ DashboardConfig برای تنظیمات متمرکز
- ✅ Utility Functions (reshape_rtl, get_color_for_key, etc.)
- ✅ Caching System با TTL

### 2. User Context & Access Control (100%)
- ✅ UserContext class برای مدیریت سطح دسترسی
- ✅ AccessLevel enum (CENTRAL_ORG, PROVINCE_UNIVERSITY, FACULTY, ADMIN)
- ✅ Data Filtering بر اساس context
- ✅ فیلدهای سازمانی به مدل User اضافه شد (province_code, university_code, faculty_code)

### 3. Data Providers (100%)
- ✅ BaseDataProvider با پشتیبانی از context filtering
- ✅ FacultyDataProvider با تمام متدهای لازم
- ✅ فیلترینگ خودکار بر اساس سطح دسترسی کاربر

### 4. Dashboard Implementation (50%)
- ✅ FacultyStatsDashboard (d1) - Refactored
- ⏳ سایر داشبوردها (d2, d3, d7, d8) - در انتظار

### 5. Routes (100%)
- ✅ dashboard_routes.py ایجاد شد
- ✅ Integration با app.py
- ✅ Backward compatibility با routes قدیمی

---

## 📋 کارهای باقی‌مانده

### اولویت بالا:
1. **Migration Script برای User Model**
   - اضافه کردن فیلدهای province_code, university_code, faculty_code به دیتابیس
   - به‌روزرسانی کاربران موجود

2. **Refactor داشبورد d2 (نقشه)**
   - استفاده از FacultyDataProvider
   - فیلترینگ بر اساس context

3. **Refactor داشبورد d3 (نقشه پردیس)**
   - استفاده از Data Provider
   - فیلترینگ بر اساس context

4. **Refactor داشبورد d7 (نسبت دانشجو به استاد)**
   - ایجاد StudentsDataProvider
   - فیلترینگ بر اساس context

5. **Refactor داشبورد d8 (LMS Monitoring)**
   - ایجاد LMSDataProvider
   - فیلترینگ بر اساس context

### اولویت متوسط:
6. **UI برای فیلترها**
   - اضافه کردن dropdown برای انتخاب استان (برای کاربران مرکزی)
   - اضافه کردن dropdown برای انتخاب دانشکده

7. **Testing**
   - Unit Tests برای Data Providers
   - Integration Tests برای Dashboards
   - Test برای UserContext

8. **Documentation**
   - راهنمای استفاده برای توسعه‌دهندگان
   - راهنمای مدیریت کاربران و سطوح دسترسی

---

## 🔧 نحوه استفاده

### ایجاد داشبورد جدید:

```python
# app/dashboards/dashboards/my_dashboard.py
from ..base import BaseDashboard
from ..data_providers.faculty import FacultyDataProvider
from ..registry import DashboardRegistry
from ..context import UserContext
from flask import render_template, make_response

@DashboardRegistry.register
class MyDashboard(BaseDashboard):
    def __init__(self):
        super().__init__(
            dashboard_id="my_dashboard",
            title="داشبورد من",
            description="توضیحات"
        )
        self.data_provider = FacultyDataProvider()
    
    def get_data(self, context: UserContext, **kwargs):
        filters = kwargs.get('filters', {})
        return {
            "data": self.data_provider.get_faculty_by_sex(context, filters)
        }
    
    def render(self, data, context):
        template_context = self.get_template_context(data, context)
        response = make_response(
            render_template("dashboards/my_dashboard.html", **template_context)
        )
        return self.add_no_cache_headers(response)
```

### تنظیم سطح دسترسی کاربر:

```python
# در app.py یا یک script مدیریتی
from models import User, AccessLevel, db

user = User.query.filter_by(sso_id="username").first()

# تنظیم سطح دسترسی
access = AccessLevel(level="province_university", user_id=user.id)
db.session.add(access)

# تنظیم اطلاعات سازمانی
user.province_code = 1  # کد استان
user.university_code = 101  # کد دانشگاه
user.faculty_code = 1001  # کد دانشکده

db.session.commit()
```

---

## 🎯 سطوح دسترسی

### 1. CENTRAL_ORG (سازمان مرکزی)
- دسترسی به تمام داده‌ها
- می‌تواند بر اساس استان/دانشکده فیلتر کند
- می‌تواند داده‌های کل کشور را ببیند

### 2. PROVINCE_UNIVERSITY (دانشگاه استان)
- فقط داده‌های استان خود
- می‌تواند بر اساس دانشکده فیلتر کند
- نمی‌تواند داده‌های استان‌های دیگر را ببیند

### 3. FACULTY (دانشکده)
- فقط داده‌های دانشکده خود
- نمی‌تواند فیلتر کند
- دسترسی محدود به داده‌های خود

### 4. ADMIN (مدیر سیستم)
- دسترسی کامل به همه داده‌ها
- می‌تواند همه فیلترها را استفاده کند

---

## 📝 نکات مهم

1. **Cache**: داشبوردها به صورت خودکار cache می‌شوند (TTL: 5-10 دقیقه)
2. **Context**: UserContext به صورت خودکار از session و User model خوانده می‌شود
3. **Filtering**: فیلترها به صورت خودکار بر اساس سطح دسترسی کاربر اعمال می‌شوند
4. **Backward Compatibility**: Routes قدیمی هنوز کار می‌کنند

---

## 🐛 مشکلات شناخته شده

1. **Migration**: فیلدهای جدید به User model اضافه شده‌اند اما migration اجرا نشده
2. **Province Mapping**: نیاز به تست mapping استان‌ها
3. **Faculty Code**: ممکن است نیاز به mapping بین code_markaz و faculty_code باشد

---

## 📚 فایل‌های ایجاد شده

```
app/
├── dashboards/
│   ├── __init__.py
│   ├── base.py
│   ├── registry.py
│   ├── context.py
│   ├── config.py
│   ├── utils.py
│   ├── cache.py
│   ├── data_providers/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── faculty.py
│   └── dashboards/
│       ├── __init__.py
│       └── faculty_stats.py
├── dashboard_routes.py
└── models.py (updated)
```

---

## 🚀 مراحل بعدی

1. اجرای Migration برای User model
2. تست داشبورد d1 با کاربران مختلف
3. Refactor داشبوردهای دیگر
4. اضافه کردن UI برای فیلترها
5. Testing و Documentation


