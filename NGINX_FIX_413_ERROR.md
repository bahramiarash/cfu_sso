# راهنمای رفع خطای 413 Request Entity Too Large

## مشکل
خطای `413 Request Entity Too Large` زمانی رخ می‌دهد که حجم فایل آپلود شده بیشتر از محدودیت تعریف شده در Nginx باشد.

## راه حل

### مرحله 1: پیدا کردن فایل تنظیمات Nginx

فایل تنظیمات Nginx معمولاً در یکی از این مسیرها قرار دارد:
- `/etc/nginx/sites-available/bi` یا `/etc/nginx/sites-available/bi.cfu.ac.ir`
- `/etc/nginx/nginx.conf`
- `/etc/nginx/conf.d/default.conf`

برای پیدا کردن فایل تنظیمات:

```bash
# جستجوی فایل‌های تنظیمات
sudo find /etc/nginx -name "*.conf" -type f

# بررسی فایل‌های فعال
sudo ls -la /etc/nginx/sites-enabled/

# جستجوی تنظیمات فعلی
sudo grep -r "bi.cfu.ac.ir" /etc/nginx/
```

### مرحله 2: ویرایش فایل تنظیمات

بعد از پیدا کردن فایل تنظیمات، آن را ویرایش کنید:

```bash
# مثال: ویرایش فایل تنظیمات
sudo nano /etc/nginx/sites-available/bi
# یا
sudo nano /etc/nginx/nginx.conf
```

### مرحله 3: اضافه کردن یا تغییر تنظیمات

در بخش `server` مربوط به `bi.cfu.ac.ir`، این تنظیمات را اضافه یا تغییر دهید:

```nginx
server {
    listen 443 ssl http2;
    server_name bi.cfu.ac.ir;

    # افزایش حد مجاز اندازه درخواست به 50M
    client_max_body_size 50M;

    # SSL certificates (اگر دارید)
    # ssl_certificate /path/to/cert.pem;
    # ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # افزایش timeout برای آپلود فایل‌های بزرگ
        proxy_read_timeout 300s;
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
    }

    location /static {
        alias /path/to/app/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

**نکات مهم:**
- `client_max_body_size 50M;` باید در بخش `server` یا `http` قرار گیرد
- `proxy_read_timeout 300s;` برای فایل‌های بزرگ ضروری است
- مسیر `/path/to/app/static` را با مسیر واقعی پروژه جایگزین کنید

### مرحله 4: بررسی صحت تنظیمات

قبل از اعمال تغییرات، صحت تنظیمات را بررسی کنید:

```bash
sudo nginx -t
```

اگر پیام `syntax is ok` و `test is successful` را دیدید، به مرحله بعد بروید.

### مرحله 5: اعمال تغییرات

بعد از بررسی صحت تنظیمات، Nginx را reload کنید:

```bash
# روش 1: Reload (توصیه می‌شود - بدون قطع سرویس)
sudo systemctl reload nginx

# روش 2: Restart (اگر reload کار نکرد)
sudo systemctl restart nginx

# بررسی وضعیت
sudo systemctl status nginx
```

### مرحله 6: بررسی تنظیمات اعمال شده

برای اطمینان از اعمال شدن تنظیمات:

```bash
# بررسی تنظیمات فعلی
sudo grep -r "client_max_body_size" /etc/nginx/

# بررسی وضعیت Nginx
sudo systemctl status nginx

# بررسی لاگ‌های Nginx (در صورت خطا)
sudo tail -f /var/log/nginx/error.log
```

## مثال کامل فایل تنظیمات

```nginx
# /etc/nginx/sites-available/bi
server {
    listen 80;
    server_name bi.cfu.ac.ir;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name bi.cfu.ac.ir;

    # SSL certificates
    ssl_certificate /etc/ssl/certs/bi.cfu.ac.ir.crt;
    ssl_certificate_key /etc/ssl/private/bi.cfu.ac.ir.key;

    # افزایش حد مجاز اندازه درخواست به 50M
    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # افزایش timeout برای آپلود فایل‌های بزرگ
        proxy_read_timeout 300s;
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
    }

    location /static {
        alias /opt/cert2/app/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

## عیب‌یابی

### اگر بعد از اعمال تغییرات هنوز خطا می‌دهد:

1. **بررسی لاگ‌های Nginx:**
   ```bash
   sudo tail -f /var/log/nginx/error.log
   ```

2. **بررسی اینکه تنظیمات درست اعمال شده:**
   ```bash
   sudo nginx -T | grep client_max_body_size
   ```

3. **بررسی اینکه Nginx درست reload شده:**
   ```bash
   sudo systemctl status nginx
   ```

4. **اگر تنظیمات در سطح `http` تعریف شده:**
   - ممکن است نیاز باشد در `/etc/nginx/nginx.conf` در بخش `http` تنظیم کنید:
   ```nginx
   http {
       client_max_body_size 50M;
       # ...
   }
   ```

5. **بررسی محدودیت‌های دیگر:**
   - ممکن است محدودیت دیگری در سطح سیستم یا فایروال وجود داشته باشد

## تنظیمات Flask

در کد Flask (`app/app.py`)، محدودیت به 50MB تنظیم شده است:
```python
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB
```

این مقدار باید با `client_max_body_size` در Nginx هماهنگ باشد.

## خلاصه دستورات

```bash
# 1. پیدا کردن فایل تنظیمات
sudo grep -r "bi.cfu.ac.ir" /etc/nginx/

# 2. ویرایش فایل (مثال)
sudo nano /etc/nginx/sites-available/bi

# 3. اضافه کردن: client_max_body_size 50M;

# 4. بررسی صحت
sudo nginx -t

# 5. اعمال تغییرات
sudo systemctl reload nginx

# 6. بررسی وضعیت
sudo systemctl status nginx
```

