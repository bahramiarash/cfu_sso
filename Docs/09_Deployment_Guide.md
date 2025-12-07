# راهنمای استقرار - سامانه BI دانشگاه فرهنگیان

## 1. مقدمه

این راهنما نحوه نصب و راه‌اندازی سامانه BI دانشگاه فرهنگیان را شرح می‌دهد.

## 2. پیش‌نیازها

### 2.1 سخت‌افزار

**حداقل**:
- CPU: 2 Core
- RAM: 4 GB
- Disk: 20 GB

**توصیه شده**:
- CPU: 4 Core
- RAM: 8 GB
- Disk: 50 GB SSD

### 2.2 نرم‌افزار

- **سیستم عامل**: Windows Server 2016+ یا Linux (Ubuntu 20.04+)
- **Python**: 3.8 یا بالاتر
- **پایگاه داده**: SQLite (پیش‌فرض) یا PostgreSQL (برای Production)
- **وب سرور**: Nginx یا Apache (برای Production)
- **WSGI Server**: Gunicorn یا Waitress

### 2.3 دسترسی‌ها

- دسترسی به SSO دانشگاه فرهنگیان
- دسترسی به API Gateway
- دسترسی به اینترنت برای نصب پکیج‌ها

## 3. نصب

### 3.1 کلون کردن پروژه

```bash
git clone <repository-url>
cd cert2
```

### 3.2 ایجاد محیط مجازی

**Windows**:
```bash
python -m venv myenv
myenv\Scripts\activate
```

**Linux**:
```bash
python3 -m venv myenv
source myenv/bin/activate
```

### 3.3 نصب وابستگی‌ها

```bash
pip install -r requirements.txt
```

### 3.4 پیکربندی محیط

فایل `.env` را در ریشه پروژه ایجاد کنید:

```env
# Secret Key (برای Session و Security)
SECRET_KEY=your-secret-key-here

# SSO Configuration
SSO_CLIENT_ID=bicfu
SSO_CLIENT_SECRET=your-sso-client-secret
SSO_AUTH_URL=https://sso.cfu.ac.ir/oauth2/authorize
SSO_TOKEN_URL=https://sso.cfu.ac.ir/oauth2/token
SSO_REDIRECT_URI=https://bi.cfu.ac.ir/authorized
SSO_SCOPE=profile email

# Admin Users (اختیاری - برای Migration)
ADMIN_USERS=admin1,admin2

# Database
DATABASE_URL=sqlite:///app/access_control.db

# Flask Configuration
FLASK_ENV=production
FLASK_DEBUG=False
```

**نکته**: `SECRET_KEY` باید یک رشته تصادفی و امن باشد. می‌توانید از دستور زیر استفاده کنید:

```python
import secrets
print(secrets.token_urlsafe(32))
```

### 3.5 ایجاد پایگاه داده

```bash
cd app
python init_db.py
```

یا از طریق Python:

```python
from app import app, db
with app.app_context():
    db.create_all()
```

### 3.6 ایجاد کاربر Admin

```bash
python add_admin_access.py
```

یا از طریق Python:

```python
from app import app, db
from models import User, AccessLevel

with app.app_context():
    user = User(
        sso_id='admin_username',
        name='Admin User'
    )
    db.session.add(user)
    db.session.commit()
    
    access = AccessLevel(level='admin', user_id=user.id)
    db.session.add(access)
    db.session.commit()
```

## 4. راه‌اندازی

### 4.1 Development Mode

```bash
cd app
python app.py
```

یا:

```bash
flask run
```

سرور روی `http://localhost:5000` اجرا می‌شود.

### 4.2 Production Mode با Waitress

```bash
cd app
waitress-serve --host=0.0.0.0 --port=5000 app:app
```

### 4.3 Production Mode با Gunicorn

```bash
cd app
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

**پارامترها**:
- `-w 4`: تعداد Worker ها
- `-b 0.0.0.0:5000`: آدرس و پورت

## 5. پیکربندی Nginx

### 5.1 فایل Configuration

`/etc/nginx/sites-available/bi`:

```nginx
server {
    listen 80;
    server_name bi.cfu.ac.ir;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name bi.cfu.ac.ir;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static {
        alias /path/to/app/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

### 5.2 فعال کردن Configuration

```bash
sudo ln -s /etc/nginx/sites-available/bi /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 6. پیکربندی Systemd Service

### 6.1 ایجاد Service File

`/etc/systemd/system/bi.service`:

```ini
[Unit]
Description=BI System Gunicorn
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/path/to/app
Environment="PATH=/path/to/myenv/bin"
ExecStart=/path/to/myenv/bin/gunicorn -w 4 -b 127.0.0.1:5000 app:app

[Install]
WantedBy=multi-user.target
```

### 6.2 فعال کردن Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable bi
sudo systemctl start bi
sudo systemctl status bi
```

## 7. پیکربندی SSL

### 7.1 استفاده از Let's Encrypt

```bash
sudo apt-get install certbot python3-certbot-nginx
sudo certbot --nginx -d bi.cfu.ac.ir
```

### 7.2 استفاده از Certificate موجود

Certificate را در مسیر مناسب قرار دهید و در Configuration Nginx اشاره کنید.

## 8. پیکربندی Firewall

```bash
# Allow HTTP
sudo ufw allow 80/tcp

# Allow HTTPS
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw enable
```

## 9. Backup

### 9.1 Backup پایگاه داده

**SQLite**:
```bash
# Backup access_control.db
sqlite3 app/access_control.db ".backup backup/access_control_$(date +%Y%m%d).db"

# Backup faculty_data.db
sqlite3 app/fetch_data/faculty_data.db ".backup backup/faculty_data_$(date +%Y%m%d).db"
```

**PostgreSQL**:
```bash
pg_dump -U username -d database_name > backup_$(date +%Y%m%d).sql
```

### 9.2 Backup خودکار

ایجاد Cron Job:

```bash
crontab -e
```

اضافه کردن:

```cron
0 2 * * * /path/to/backup_script.sh
```

## 10. Monitoring

### 10.1 Log Files

**Application Logs**:
- `app/app.log`

**System Logs**:
- `/var/log/nginx/access.log`
- `/var/log/nginx/error.log`
- `/var/log/systemd/bi.service`

### 10.2 Health Check

ایجاد Endpoint برای Health Check:

```python
@app.route('/health')
def health():
    return jsonify({'status': 'ok'}), 200
```

## 11. به‌روزرسانی

### 11.1 به‌روزرسانی کد

```bash
git pull origin main
pip install -r requirements.txt
sudo systemctl restart bi
```

### 11.2 Migration پایگاه داده

```bash
cd app/migrations
python <migration_file>.py
```

## 12. Troubleshooting

### 12.1 مشکلات رایج

**خطای Import**:
- بررسی کنید که محیط مجازی فعال است
- بررسی کنید که همه پکیج‌ها نصب شده‌اند

**خطای Database**:
- بررسی کنید که فایل پایگاه داده وجود دارد
- بررسی کنید که دسترسی‌های فایل درست است

**خطای SSO**:
- بررسی کنید که تنظیمات SSO در `.env` صحیح است
- بررسی کنید که Redirect URI در SSO ثبت شده است

**خطای Port**:
- بررسی کنید که پورت 5000 آزاد است
- یا پورت دیگری را استفاده کنید

### 12.2 لاگ‌ها

برای مشاهده لاگ‌ها:

```bash
# Application logs
tail -f app/app.log

# Systemd logs
sudo journalctl -u bi -f

# Nginx logs
sudo tail -f /var/log/nginx/error.log
```

## 13. امنیت

### 13.1 توصیه‌های امنیتی

- استفاده از HTTPS
- تنظیم SECRET_KEY قوی
- محدود کردن دسترسی به فایل‌های حساس
- به‌روزرسانی منظم پکیج‌ها
- استفاده از Firewall
- محدود کردن دسترسی Admin

### 13.2 Hardening

- غیرفعال کردن Debug Mode در Production
- تنظیم SECURE_COOKIE
- استفاده از HTTPONLY و SAMESITE برای Cookies
- محدود کردن Rate Limiting

## 14. Performance

### 14.1 بهینه‌سازی

- استفاده از Cache
- بهینه‌سازی Query ها
- استفاده از CDN برای Static Files
- استفاده از Compression (gzip)

### 14.2 Monitoring

- استفاده از Monitoring Tools (Prometheus, Grafana)
- تنظیم Alerting
- بررسی Performance Metrics

## 15. مقیاس‌پذیری

### 15.1 Load Balancing

استفاده از چندین Instance با Load Balancer:

```nginx
upstream bi_backend {
    server 127.0.0.1:5000;
    server 127.0.0.1:5001;
    server 127.0.0.1:5002;
}

server {
    ...
    location / {
        proxy_pass http://bi_backend;
    }
}
```

### 15.2 Database Scaling

- مهاجرت به PostgreSQL
- استفاده از Connection Pooling
- استفاده از Read Replicas

## 16. شروع سریع

برای شروع سریع:

```bash
# 1. Clone repository
git clone <repository-url>
cd cert2

# 2. Create virtual environment
python -m venv myenv
source myenv/bin/activate  # Linux
# یا
myenv\Scripts\activate  # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env file
cp .env.example .env
# ویرایش .env و تنظیم مقادیر

# 5. Initialize database
cd app
python init_db.py

# 6. Create admin user
python add_admin_access.py

# 7. Run application
python app.py
```

## 17. چک‌لیست استقرار

- [ ] Python 3.8+ نصب شده
- [ ] محیط مجازی ایجاد شده
- [ ] وابستگی‌ها نصب شده
- [ ] فایل `.env` ایجاد و پیکربندی شده
- [ ] پایگاه داده ایجاد شده
- [ ] کاربر Admin ایجاد شده
- [ ] SSL Certificate تنظیم شده
- [ ] Nginx پیکربندی شده
- [ ] Systemd Service تنظیم شده
- [ ] Firewall پیکربندی شده
- [ ] Backup تنظیم شده
- [ ] Monitoring تنظیم شده

---

**تاریخ ایجاد**: 1404  
**آخرین به‌روزرسانی**: 1404

