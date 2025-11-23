# راهنمای تست سیستم داشبوردها

## 📋 فهرست مطالب

1. [تست Migration](#1-تست-migration)
2. [تست User Context](#2-تست-user-context)
3. [تست داشبوردها](#3-تست-داشبوردها)
4. [تست فیلترها](#4-تست-فیلترها)
5. [تست با کاربران مختلف](#5-تست-با-کاربران-مختلف)
6. [اجرای Unit Tests](#6-اجرای-unit-tests)
7. [اجرای Integration Tests](#7-اجرای-integration-tests)

---

## 1. تست Migration

### بررسی فیلدهای اضافه شده:

```python
# در Python shell یا script
import sqlite3

conn = sqlite3.connect('app/access_control.db')
cursor = conn.cursor()

# بررسی ساختار جدول users
cursor.execute("PRAGMA table_info(users)")
columns = cursor.fetchall()

for col in columns:
    print(f"{col[1]} - {col[2]}")

# باید فیلدهای زیر را ببینید:
# - province_code (INTEGER)
# - university_code (INTEGER)
# - faculty_code (INTEGER)

conn.close()
```

### تست دستی:

```bash
# در PowerShell یا CMD
cd app
python migrations/add_user_org_fields.py
```

---

## 2. تست User Context

### ایجاد کاربر تست:

```python
# در Python shell (از دایرکتوری app)
from app import app
from models import db, User, AccessLevel
from dashboards.context import UserContext

with app.app_context():
    # ایجاد کاربر تست - سازمان مرکزی
    user1 = User(
        sso_id='test_central',
        name='کاربر مرکزی',
        email='central@test.com'
    )
    db.session.add(user1)
    db.session.flush()
    
    access1 = AccessLevel(level='central_org', user_id=user1.id)
    db.session.add(access1)
    
    # ایجاد کاربر تست - دانشگاه استان
    user2 = User(
        sso_id='test_province',
        name='کاربر استان',
        email='province@test.com',
        province_code=1  # تهران
    )
    db.session.add(user2)
    db.session.flush()
    
    access2 = AccessLevel(level='province_university', user_id=user2.id)
    db.session.add(access2)
    
    # ایجاد کاربر تست - دانشکده
    user3 = User(
        sso_id='test_faculty',
        name='کاربر دانشکده',
        email='faculty@test.com',
        province_code=1,
        faculty_code=1001
    )
    db.session.add(user3)
    db.session.flush()
    
    access3 = AccessLevel(level='faculty', user_id=user3.id)
    db.session.add(access3)
    
    db.session.commit()
    
    # تست UserContext
    context1 = UserContext(user1, {})
    print(f"User 1 - Access Level: {context1.access_level.value}")
    print(f"User 1 - Can filter by province: {context1.data_filters['can_filter_by_province']}")
    
    context2 = UserContext(user2, {})
    print(f"User 2 - Access Level: {context2.access_level.value}")
    print(f"User 2 - Province Code: {context2.province_code}")
    
    context3 = UserContext(user3, {})
    print(f"User 3 - Access Level: {context3.access_level.value}")
    print(f"User 3 - Faculty Code: {context3.faculty_code}")
```

---

## 3. تست داشبوردها

### 3.1. تست از طریق مرورگر

1. **اجرای سرور:**
```bash
cd app
python app.py
```

2. **ورود به سیستم:**
   - به `http://localhost:5000` بروید
   - با یکی از کاربران تست وارد شوید

3. **بررسی لیست داشبوردها:**
   - به `/dashboards` بروید
   - باید لیست داشبوردهای قابل دسترسی را ببینید

4. **تست هر داشبورد:**
   - `/dashboards/d1` - آمار اعضای هیئت علمی
   - `/dashboards/d2` - نقشه توزیع
   - `/dashboards/d3` - نقشه پردیس‌ها
   - `/dashboards/d7` - نسبت دانشجو به استاد
   - `/dashboards/d8` - مانیتورینگ LMS

### 3.2. تست از طریق Python

```python
from app import app
from flask_login import login_user
from models import User
from dashboards.registry import DashboardRegistry
from dashboards.context import get_user_context

with app.test_client() as client:
    with app.app_context():
        # ورود کاربر
        user = User.query.filter_by(sso_id='test_central').first()
        login_user(user)
        
        # دریافت context
        context = get_user_context(user)
        
        # تست داشبورد
        dashboard = DashboardRegistry.get('d1')
        if dashboard:
            # تست get_data
            data = dashboard.get_data(context)
            print(f"Dashboard d1 data keys: {data.keys()}")
            
            # تست render
            response = dashboard.render(data, context)
            print(f"Response status: {response.status_code}")
```

---

## 4. تست فیلترها

### 4.1. تست API فیلترها

```python
from app import app
from flask_login import login_user
from models import User

with app.test_client() as client:
    with app.app_context():
        # ورود کاربر
        user = User.query.filter_by(sso_id='test_central').first()
        login_user(user)
        
        # تست API provinces
        response = client.get('/api/dashboards/provinces')
        print(f"Provinces API: {response.status_code}")
        print(f"Data: {response.get_json()}")
        
        # تست API faculties
        response = client.get('/api/dashboards/faculties')
        print(f"Faculties API: {response.status_code}")
        print(f"Data: {response.get_json()}")
```

### 4.2. تست فیلتر در داشبورد

```python
from app import app
from flask_login import login_user
from models import User
from dashboards.registry import DashboardRegistry
from dashboards.context import get_user_context

with app.test_client() as client:
    with app.app_context():
        user = User.query.filter_by(sso_id='test_central').first()
        login_user(user)
        context = get_user_context(user)
        
        dashboard = DashboardRegistry.get('d1')
        
        # تست با فیلتر استان
        filters = {'province_code': 1}
        data = dashboard.get_data(context, filters=filters)
        print(f"Data with province filter: {len(data.get('sex_data', {}).get('labels', []))} items")
        
        # تست با فیلتر دانشکده
        filters = {'faculty_code': 1001}
        data = dashboard.get_data(context, filters=filters)
        print(f"Data with faculty filter: {len(data.get('sex_data', {}).get('labels', []))} items")
```

### 4.3. تست از طریق URL

در مرورگر:
```
http://localhost:5000/dashboards/d1?province_code=1
http://localhost:5000/dashboards/d1?faculty_code=1001
```

---

## 5. تست با کاربران مختلف

### 5.1. اسکریپت تست کامل

```python
# test_user_access.py
from app import app
from models import db, User, AccessLevel
from dashboards.registry import DashboardRegistry
from dashboards.context import UserContext

def test_user_access():
    with app.app_context():
        # کاربر سازمان مرکزی
        user_central = User.query.filter_by(sso_id='test_central').first()
        context_central = UserContext(user_central, {})
        
        print("=" * 50)
        print("تست کاربر سازمان مرکزی")
        print("=" * 50)
        print(f"Access Level: {context_central.access_level.value}")
        print(f"Can filter by province: {context_central.data_filters['can_filter_by_province']}")
        print(f"Can filter by faculty: {context_central.data_filters['can_filter_by_faculty']}")
        
        # تست داشبورد
        dashboard = DashboardRegistry.get('d1')
        data = dashboard.get_data(context_central)
        print(f"Data received: {len(data)} items")
        
        # کاربر دانشگاه استان
        user_province = User.query.filter_by(sso_id='test_province').first()
        context_province = UserContext(user_province, {})
        
        print("\n" + "=" * 50)
        print("تست کاربر دانشگاه استان")
        print("=" * 50)
        print(f"Access Level: {context_province.access_level.value}")
        print(f"Province Code: {context_province.province_code}")
        print(f"Can filter by province: {context_province.data_filters['can_filter_by_province']}")
        
        # تست داشبورد
        data = dashboard.get_data(context_province)
        print(f"Data received: {len(data)} items")
        
        # کاربر دانشکده
        user_faculty = User.query.filter_by(sso_id='test_faculty').first()
        context_faculty = UserContext(user_faculty, {})
        
        print("\n" + "=" * 50)
        print("تست کاربر دانشکده")
        print("=" * 50)
        print(f"Access Level: {context_faculty.access_level.value}")
        print(f"Faculty Code: {context_faculty.faculty_code}")
        print(f"Can filter by province: {context_faculty.data_filters['can_filter_by_province']}")
        
        # تست داشبورد
        data = dashboard.get_data(context_faculty)
        print(f"Data received: {len(data)} items")

if __name__ == '__main__':
    test_user_access()
```

اجرا:
```bash
cd app
python test_user_access.py
```

---

## 6. اجرای Unit Tests

### 6.1. نصب pytest (اختیاری اما توصیه می‌شود):

```bash
pip install pytest pytest-cov
```

### 6.2. اجرای تست‌ها:

```bash
# از دایرکتوری root پروژه
python -m pytest tests/test_dashboards.py -v

# یا با coverage
python -m pytest tests/test_dashboards.py --cov=app.dashboards --cov-report=html
```

### 6.3. اجرای تست‌های خاص:

```bash
# فقط تست UserContext
python -m pytest tests/test_dashboards.py::TestUserContext -v

# فقط تست Data Provider
python -m pytest tests/test_dashboards.py::TestFacultyDataProvider -v
```

---

## 7. اجرای Integration Tests

```bash
python -m pytest tests/test_integration.py -v
```

---

## 8. چک‌لیست تست کامل

### ✅ Migration
- [ ] فیلدهای جدید در دیتابیس اضافه شده‌اند
- [ ] Migration بدون خطا اجرا می‌شود

### ✅ User Context
- [ ] کاربر مرکزی می‌تواند همه داده‌ها را ببیند
- [ ] کاربر استان فقط داده‌های استان خود را می‌بیند
- [ ] کاربر دانشکده فقط داده‌های دانشکده خود را می‌بیند
- [ ] فیلترها به درستی اعمال می‌شوند

### ✅ داشبوردها
- [ ] d1 - آمار اعضای هیئت علمی
- [ ] d2 - نقشه توزیع
- [ ] d3 - نقشه پردیس‌ها
- [ ] d7 - نسبت دانشجو به استاد
- [ ] d8 - مانیتورینگ LMS

### ✅ فیلترها
- [ ] API provinces کار می‌کند
- [ ] API faculties کار می‌کند
- [ ] فیلتر استان در داشبورد کار می‌کند
- [ ] فیلتر دانشکده در داشبورد کار می‌کند

### ✅ Cache
- [ ] Cache برای query‌های سنگین فعال است
- [ ] Cache بعد از TTL منقضی می‌شود

### ✅ Security
- [ ] کاربران نمی‌توانند داده‌های غیرمجاز را ببینند
- [ ] فیلترها به درستی اعمال می‌شوند

---

## 9. اسکریپت تست خودکار

```python
# run_tests.py
import sys
import os

# اضافه کردن مسیر app به path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app import app
from models import db, User, AccessLevel
from dashboards.registry import DashboardRegistry
from dashboards.context import UserContext

def run_all_tests():
    """اجرای تمام تست‌ها"""
    print("شروع تست‌ها...\n")
    
    with app.app_context():
        # تست 1: بررسی داشبوردها
        print("1. تست Registry...")
        dashboards = DashboardRegistry.list_all()
        print(f"   ✓ {len(dashboards)} داشبورد ثبت شده")
        
        # تست 2: بررسی User Context
        print("\n2. تست User Context...")
        user = User.query.first()
        if user:
            context = UserContext(user, {})
            print(f"   ✓ UserContext ایجاد شد: {context.access_level.value}")
        else:
            print("   ⚠ کاربری یافت نشد")
        
        # تست 3: تست داشبوردها
        print("\n3. تست داشبوردها...")
        for dashboard in dashboards:
            try:
                if user:
                    context = UserContext(user, {})
                    data = dashboard.get_data(context)
                    print(f"   ✓ {dashboard.dashboard_id}: {len(data)} آیتم داده")
                else:
                    print(f"   ⚠ {dashboard.dashboard_id}: نیاز به کاربر")
            except Exception as e:
                print(f"   ✗ {dashboard.dashboard_id}: خطا - {e}")
        
        print("\n✓ تست‌ها کامل شد!")

if __name__ == '__main__':
    run_all_tests()
```

اجرا:
```bash
python run_tests.py
```

---

## 10. عیب‌یابی

### مشکل: داشبورد خطا می‌دهد
- بررسی کنید که دیتابیس‌ها موجود هستند
- بررسی کنید که کاربر وارد سیستم شده است
- لاگ‌ها را بررسی کنید

### مشکل: فیلتر کار نمی‌کند
- بررسی کنید که سطح دسترسی کاربر درست است
- بررسی کنید که API endpoints کار می‌کنند
- بررسی کنید که JavaScript در مرورگر فعال است

### مشکل: داده‌های اشتباه نمایش داده می‌شود
- بررسی کنید که province_code, faculty_code درست تنظیم شده
- Cache را پاک کنید
- بررسی کنید که context به درستی ایجاد می‌شود

---

## 11. تست Performance

```python
import time
from dashboards.registry import DashboardRegistry
from dashboards.context import get_user_context

def test_performance():
    """تست عملکرد داشبوردها"""
    dashboard = DashboardRegistry.get('d1')
    context = get_user_context()
    
    # تست بدون cache
    start = time.time()
    data1 = dashboard.get_data(context)
    time1 = time.time() - start
    print(f"بدون cache: {time1:.2f} ثانیه")
    
    # تست با cache
    start = time.time()
    data2 = dashboard.get_data(context)
    time2 = time.time() - start
    print(f"با cache: {time2:.2f} ثانیه")
    print(f"بهبود: {((time1 - time2) / time1 * 100):.1f}%")
```

---

## 📝 نکات مهم

1. **همیشه با کاربران مختلف تست کنید**
2. **Cache را در نظر بگیرید** - ممکن است نیاز به پاک کردن cache باشد
3. **لاگ‌ها را بررسی کنید** - خطاها در لاگ‌ها ثبت می‌شوند
4. **دیتابیس را بررسی کنید** - مطمئن شوید که داده‌ها موجود هستند

---

## 🎯 نتیجه

با انجام این تست‌ها می‌توانید مطمئن شوید که:
- ✅ سیستم به درستی کار می‌کند
- ✅ فیلترها درست اعمال می‌شوند
- ✅ امنیت رعایت شده است
- ✅ Performance قابل قبول است

