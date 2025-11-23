# راهنمای تنظیم متغیرهای محیطی

این فایل راهنمای تنظیم متغیرهای محیطی مورد نیاز برای اجرای پروژه است.

## نصب و راه‌اندازی

1. فایل `.env` را در ریشه پروژه ایجاد کنید
2. مقادیر زیر را با اطلاعات واقعی پر کنید:

```env
# Flask Application Configuration

# Flask Secret Key (required)
# برای تولید یک کلید امن تصادفی از دستور زیر استفاده کنید:
# python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=your-secure-random-key-here

# SSO Configuration (required)
SSO_CLIENT_ID=bicfu
SSO_CLIENT_SECRET=your-sso-client-secret-here
SSO_AUTH_URL=https://sso.cfu.ac.ir/oauth2/authorize
SSO_TOKEN_URL=https://sso.cfu.ac.ir/oauth2/token
SSO_SCOPE=profile email
SSO_REDIRECT_URI=https://bi.cfu.ac.ir/authorized

# SMS Service Configuration (required)
SMS_USER=your-sms-username
SMS_PASS=your-sms-password
SMS_ADMIN_NUMBERS=09123880167,09121451151

# Admin Users (optional - comma-separated list of SSO usernames)
# اگر تنظیم نشود، سیستم از کنترل دسترسی مبتنی بر دیتابیس استفاده می‌کند
# مثال: ADMIN_USERS=bahrami,khodarahmi,asef
ADMIN_USERS=
```

## نکات امنیتی

⚠️ **مهم**: 
- هرگز فایل `.env` را به git commit نکنید
- فایل `.env` در `.gitignore` قرار دارد
- تمام اطلاعات حساس باید در متغیرهای محیطی قرار گیرند
- در production، از متغیرهای محیطی سیستم عامل استفاده کنید

## تولید Secret Key

برای تولید یک SECRET_KEY امن، از دستور زیر استفاده کنید:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

یا در Python:

```python
import secrets
print(secrets.token_hex(32))
```

## مدیریت دسترسی کاربران

سیستم از دو روش برای مدیریت دسترسی استفاده می‌کند:

1. **دیتابیس**: کاربران با نقش `admin` در جدول `access_levels`
2. **متغیر محیطی**: لیست کاربران در `ADMIN_USERS` (برای migration)

برای اضافه کردن کاربر به دیتابیس:

```python
from app import app
from models import db, User, AccessLevel

with app.app_context():
    user = User.query.filter_by(sso_id='username').first()
    if user:
        admin_access = AccessLevel(level='admin', user_id=user.id)
        db.session.add(admin_access)
        db.session.commit()
```

## عیب‌یابی

اگر خطای زیر را دریافت کردید:

```
ValueError: SECRET_KEY environment variable is not set
```

یا

```
ValueError: SSO_CLIENT_SECRET environment variable is not set
```

مطمئن شوید که:
1. فایل `.env` در ریشه پروژه وجود دارد
2. تمام متغیرهای مورد نیاز در `.env` تنظیم شده‌اند
3. `python-dotenv` نصب شده است: `pip install python-dotenv`

