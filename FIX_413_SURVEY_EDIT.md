# راهنمای رفع خطای 413 در صفحه ویرایش نظرسنجی

## مشکل
هنگام ذخیره فرم ویرایش نظرسنجی با "نوع دسترسی: بدون احراز هویت"، خطای زیر رخ می‌دهد:
```
413 Request Entity Too Large
nginx/1.24.0
```

## علت مشکل
وقتی "نوع دسترسی" روی "بدون احراز هویت" تنظیم می‌شود، بخش "پارامترهای URL" نمایش داده می‌شود. اگر کاربر چندین پارامتر با مقادیر زیاد تعریف کند، حجم درخواست POST از حد مجاز nginx (که به طور پیش‌فرض 1MB است) بیشتر می‌شود.

## راه حل

### مرحله 1: پیدا کردن فایل تنظیمات Nginx

```bash
# جستجوی فایل تنظیمات مربوط به bi.cfu.ac.ir
sudo grep -r "bi.cfu.ac.ir" /etc/nginx/

# بررسی فایل‌های فعال
sudo ls -la /etc/nginx/sites-enabled/

# پیدا کردن فایل تنظیمات
sudo find /etc/nginx -name "*.conf" -type f | xargs grep -l "bi.cfu.ac.ir"
```

### مرحله 2: ویرایش فایل تنظیمات

فایل تنظیمات را ویرایش کنید (معمولاً `/etc/nginx/sites-available/bi` یا `/etc/nginx/sites-available/bi.cfu.ac.ir`):

```bash
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
        
        # افزایش timeout برای درخواست‌های بزرگ
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
- اگر در سطح `http` در `/etc/nginx/nginx.conf` تنظیم شده باشد، نیازی به تنظیم مجدد در `server` نیست
- `proxy_read_timeout 300s;` برای درخواست‌های بزرگ ضروری است

### مرحله 4: بررسی صحت تنظیمات

```bash
sudo nginx -t
```

اگر پیام `syntax is ok` و `test is successful` را دیدید، به مرحله بعد بروید.

### مرحله 5: اعمال تغییرات

```bash
# روش 1: Reload (توصیه می‌شود - بدون قطع سرویس)
sudo systemctl reload nginx

# روش 2: Restart (اگر reload کار نکرد)
sudo systemctl restart nginx

# بررسی وضعیت
sudo systemctl status nginx
```

### مرحله 6: بررسی تنظیمات اعمال شده

```bash
# بررسی تنظیمات فعلی
sudo grep -r "client_max_body_size" /etc/nginx/

# بررسی کامل تنظیمات
sudo nginx -T | grep client_max_body_size

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
        
        # افزایش timeout برای درخواست‌های بزرگ
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

## توضیحات فنی

- **مقدار پیش‌فرض nginx:** 1MB
- **مقدار پیشنهادی:** 50MB (برای پشتیبانی از پارامترهای URL و فایل‌های لوگو)
- **محدودیت Flask:** در حال حاضر محدودیتی در کد Flask وجود ندارد، اما nginx قبل از رسیدن به Flask درخواست را رد می‌کند

## نکات امنیتی

- افزایش `client_max_body_size` باید با احتیاط انجام شود
- 50MB برای استفاده عادی کافی است
- اگر نیاز به مقدار بیشتر دارید، می‌توانید تا 100MB افزایش دهید، اما بیشتر از آن توصیه نمی‌شود

