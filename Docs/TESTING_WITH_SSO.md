# راهنمای تست با SSO

## 🔐 مشکل SSO با localhost

SSO معمولاً فقط با دامنه‌های ثبت‌شده کار می‌کند و با `localhost` کار نمی‌کند. برای تست، دو راه دارید:

---

## ✅ راه حل 1: استفاده از دامنه واقعی (توصیه می‌شود)

### مراحل:

1. **استفاده از دامنه واقعی:**
   ```
   https://bi.cfu.ac.ir/dashboards
   ```

2. **بعد از لاگین SSO:**
   - باید به صفحه لیست داشبوردها redirect شوید
   - این صفحه همان صفحه‌ای است که در تصویر می‌بینید

3. **بررسی اینکه از معماری جدید استفاده می‌کند:**
   - روی یکی از داشبوردها کلیک کنید (مثلاً "آمار کلی اعضای هیات علمی")
   - بررسی کنید که فیلترها نمایش داده می‌شوند (برای کاربران مرکزی)
   - بررسی کنید که داده‌ها بر اساس سطح دسترسی فیلتر می‌شوند

---

## ✅ راه حل 2: Mock SSO برای تست محلی

اگر می‌خواهید در localhost تست کنید، می‌توانید SSO را mock کنید:

### ایجاد Mock SSO:

```python
# app/mock_sso.py
from flask import session, redirect, url_for
from models import User, AccessLevel, db

def mock_sso_login(username, access_level='central_org', province_code=None, faculty_code=None):
    """
    Mock SSO login for testing
    Usage: /mock_login?username=test_central&access_level=central_org
    """
    # Find or create user
    user = User.query.filter_by(sso_id=username).first()
    if not user:
        user = User(
            sso_id=username,
            name=f'Test User {username}',
            email=f'{username}@test.com',
            province_code=province_code,
            faculty_code=faculty_code
        )
        db.session.add(user)
        db.session.flush()
    
    # Set access level
    access = AccessLevel.query.filter_by(user_id=user.id, level=access_level).first()
    if not access:
        access = AccessLevel(level=access_level, user_id=user.id)
        db.session.add(access)
    
    db.session.commit()
    
    # Set session
    session['user_info'] = {
        'username': username,
        'fullname': user.name,
        'usertype': access_level,
        'province_code': province_code,
        'faculty_code': faculty_code
    }
    session['access_level'] = [access_level]
    
    from flask_login import login_user
    login_user(user)
    
    return redirect(url_for('dashboard.dashboard_list'))
```

### اضافه کردن Route:

```python
# در app.py (فقط برای development)
if app.config.get('DEBUG'):
    @app.route('/mock_login')
    def mock_login():
        from app.mock_sso import mock_sso_login
        username = request.args.get('username', 'test_central')
        access_level = request.args.get('access_level', 'central_org')
        province_code = request.args.get('province_code', type=int)
        faculty_code = request.args.get('faculty_code', type=int)
        return mock_sso_login(username, access_level, province_code, faculty_code)
```

### استفاده:

```
http://localhost:5000/mock_login?username=test_central&access_level=central_org
http://localhost:5000/mock_login?username=test_province&access_level=province_university&province_code=1
http://localhost:5000/mock_login?username=test_faculty&access_level=faculty&province_code=1&faculty_code=1001
```

---

## 🔍 بررسی اینکه از معماری جدید استفاده می‌کند

### 1. بررسی URL داشبوردها:

صفحه لیست داشبوردها باید از route جدید استفاده کند:
- Route جدید: `/dashboards/<dashboard_id>`
- Route قدیمی: `/dashboards/d1`, `/dashboards/d2`, etc.

### 2. بررسی فیلترها:

برای کاربران مرکزی، باید فیلترها نمایش داده شوند:
- Dropdown برای انتخاب استان
- Dropdown برای انتخاب دانشکده

### 3. بررسی Console مرورگر:

در Developer Tools (F12)، بررسی کنید:
- آیا خطای JavaScript وجود دارد؟
- آیا API calls به `/api/dashboards/provinces` انجام می‌شود؟

### 4. بررسی Network Tab:

بررسی کنید که:
- Request به `/dashboards/d1` انجام می‌شود
- Response شامل داده‌های فیلتر شده است

---

## 📋 چک‌لیست تست با SSO

### ✅ صفحه لیست داشبوردها:
- [ ] صفحه لیست داشبوردها نمایش داده می‌شود
- [ ] لیست داشبوردها کامل است
- [ ] جستجو کار می‌کند

### ✅ داشبوردها:
- [ ] d1 - آمار کلی اعضای هیات علمی
- [ ] d2 - نقشه توزیع جنسیتی
- [ ] d3 - نقشه توزیع پردیس‌ها
- [ ] d7 - دانشجو معلمان
- [ ] d8 - زون‌های LMS

### ✅ فیلترها (برای کاربران مرکزی):
- [ ] فیلتر استان نمایش داده می‌شود
- [ ] فیلتر دانشکده نمایش داده می‌شود
- [ ] فیلترها کار می‌کنند

### ✅ دسترسی:
- [ ] کاربران مرکزی همه داده‌ها را می‌بینند
- [ ] کاربران استان فقط داده‌های استان خود را می‌بینند
- [ ] کاربران دانشکده فقط داده‌های دانشکده خود را می‌بینند

---

## 🐛 عیب‌یابی

### مشکل: صفحه لیست داشبوردها نمایش داده نمی‌شود
**راه‌حل:**
- بررسی کنید که route `/dashboards` در `dashboard_routes.py` وجود دارد
- بررسی کنید که blueprint ثبت شده است

### مشکل: فیلترها نمایش داده نمی‌شوند
**راه‌حل:**
- بررسی کنید که `user_context` به template پاس داده می‌شود
- بررسی کنید که `can_filter_by_province` درست است
- بررسی کنید که template `_filters.html` include شده است

### مشکل: داده‌های اشتباه نمایش داده می‌شود
**راه‌حل:**
- بررسی کنید که `UserContext` به درستی ایجاد می‌شود
- بررسی کنید که `province_code`, `faculty_code` درست تنظیم شده
- بررسی کنید که فیلترها در Data Provider اعمال می‌شوند

---

## 💡 نکات مهم

1. **برای تست محلی:** از Mock SSO استفاده کنید
2. **برای تست واقعی:** از دامنه واقعی استفاده کنید
3. **بررسی معماری:** مطمئن شوید که از معماری جدید استفاده می‌شود
4. **لاگ‌ها:** لاگ‌های سرور را بررسی کنید

---

## 🎯 نتیجه

بله، صفحه‌ای که می‌بینید همان صفحه لیست داشبوردها است. برای اطمینان از اینکه از معماری جدید استفاده می‌کند:

1. روی یکی از داشبوردها کلیک کنید
2. بررسی کنید که فیلترها نمایش داده می‌شوند (برای کاربران مرکزی)
3. بررسی کنید که داده‌ها بر اساس سطح دسترسی فیلتر می‌شوند

اگر فیلترها نمایش داده نمی‌شوند یا داده‌ها فیلتر نمی‌شوند، باید template‌ها را به‌روزرسانی کنیم.

