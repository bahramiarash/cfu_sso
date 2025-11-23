# راهنمای فعال‌سازی پنل مدیریت

## پیش‌نیازها

### 1. اجرای Migration

قبل از استفاده از پنل ادمین، باید جداول پایگاه داده ایجاد شوند:

```bash
cd app/migrations
python create_admin_tables.py
```

یا از PowerShell:

```powershell
cd app\migrations
python create_admin_tables.py
```

این دستور جداول زیر را ایجاد می‌کند:
- `dashboard_access` - دسترسی کاربران به داشبوردها
- `access_logs` - لاگ اقدامات کاربران
- `data_syncs` - وضعیت همگام‌سازی داده
- `dashboard_configs` - تنظیمات داشبوردها

### 2. بررسی دسترسی کاربر

کاربر باید سطح دسترسی `admin` یا `staff` داشته باشد. برای بررسی:

1. وارد سیستم شوید
2. بررسی کنید که کاربر شما در جدول `users` دارای `AccessLevel` با `level='admin'` یا `level='staff'` است

برای اضافه کردن دسترسی admin به یک کاربر:

```python
from models import User, AccessLevel
from extensions import db

user = User.query.filter_by(sso_id='your_username').first()
if user:
    admin_access = AccessLevel(level='admin', user_id=user.id)
    db.session.add(admin_access)
    db.session.commit()
```

## اجرای سرور

### روش 1: اجرای مستقیم app.py

```bash
python app/app.py
```

یا از PowerShell:

```powershell
python .\app\app.py
```

### روش 2: استفاده از waitress (پیشنهادی برای production)

```bash
waitress-serve --host=0.0.0.0 --port=5000 app.app:app
```

## دسترسی به پنل

پس از راه‌اندازی سرور، به آدرس زیر بروید:

```
http://localhost:5000/admin
```

یا در production:

```
https://bi.cfu.ac.ir/admin
```

## بررسی مشکلات احتمالی

### خطای "Not Found"
- مطمئن شوید که Blueprint به درستی ثبت شده است
- بررسی کنید که `app.register_blueprint(admin_bp)` در `app.py` وجود دارد

### خطای "Internal Server Error"
- لاگ‌های سرور را بررسی کنید
- مطمئن شوید که migration اجرا شده است
- بررسی کنید که مدل‌های admin_models به درستی import شده‌اند

### خطای "403 Forbidden" یا "Access Denied"
- مطمئن شوید که کاربر شما سطح دسترسی admin دارد
- بررسی کنید که `current_user.is_admin()` مقدار `True` برمی‌گرداند

## ساختار فایل‌ها

```
app/
├── admin/
│   ├── __init__.py          # Blueprint definition
│   ├── routes.py            # Admin routes
│   └── utils.py             # Helper functions
├── admin_models.py          # Admin database models
├── templates/
│   └── admin/               # Admin templates
│       ├── base.html
│       ├── index.html
│       ├── users/
│       ├── logs/
│       ├── data_sync/
│       └── dashboards/
└── migrations/
    └── create_admin_tables.py
```

## ویژگی‌های پنل

✅ مدیریت کاربران
✅ مدیریت دسترسی‌ها
✅ مشاهده لاگ‌ها
✅ مدیریت همگام‌سازی داده
✅ تنظیمات داشبوردها

## نکات مهم

1. **امنیت:** تمام routes با `@admin_required` محافظت می‌شوند
2. **لاگینگ:** تمام اقدامات در `access_logs` ثبت می‌شوند
3. **دیتابیس:** جداول باید قبل از استفاده ایجاد شوند
4. **دسترسی:** فقط کاربران admin می‌توانند به پنل دسترسی داشته باشند

