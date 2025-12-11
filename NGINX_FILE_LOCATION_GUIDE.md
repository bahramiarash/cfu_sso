# راهنمای پیدا کردن و تنظیم فایل Nginx برای حجم آپلود

## فایل‌های ممکن Nginx

حجم فایل آپلود (`client_max_body_size`) باید در یکی از این فایل‌ها تنظیم شود:

### 1. فایل تنظیمات سایت (توصیه می‌شود)
```
/etc/nginx/sites-available/bi
یا
/etc/nginx/sites-available/bi.cfu.ac.ir
```

### 2. فایل تنظیمات اصلی
```
/etc/nginx/nginx.conf
```

### 3. فایل‌های در conf.d
```
/etc/nginx/conf.d/default.conf
یا
/etc/nginx/conf.d/bi.conf
```

## چگونه فایل را پیدا کنیم؟

### روش 1: جستجوی خودکار
```bash
# جستجوی فایل‌های مربوط به bi.cfu.ac.ir
sudo grep -r "bi.cfu.ac.ir" /etc/nginx/

# پیدا کردن فایل‌های فعال
sudo ls -la /etc/nginx/sites-enabled/

# پیدا کردن فایل تنظیمات
sudo find /etc/nginx -name "*.conf" -type f | xargs grep -l "bi.cfu.ac.ir"
```

### روش 2: بررسی فایل‌های sites-available
```bash
# لیست فایل‌های موجود
sudo ls -la /etc/nginx/sites-available/

# بررسی محتوای فایل‌ها
sudo cat /etc/nginx/sites-available/bi
```

### روش 3: بررسی فایل اصلی nginx.conf
```bash
# بررسی فایل اصلی
sudo cat /etc/nginx/nginx.conf | grep -A 10 "include"
```

## کجا باید تنظیمات را اضافه کنیم؟

### گزینه 1: در بخش `server` (توصیه می‌شود)
اگر فایل تنظیمات سایت دارید (مثلاً `/etc/nginx/sites-available/bi`):

```nginx
server {
    listen 443 ssl http2;
    server_name bi.cfu.ac.ir;

    # این خط را اضافه کنید:
    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # این خطوط را نیز اضافه کنید:
        proxy_read_timeout 300s;
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
    }
}
```

### گزینه 2: در بخش `http` (برای همه سایت‌ها)
اگر می‌خواهید برای همه سایت‌ها اعمال شود، در `/etc/nginx/nginx.conf`:

```nginx
http {
    # این خط را اضافه کنید:
    client_max_body_size 50M;
    
    # ... سایر تنظیمات
}
```

## مراحل کامل

### مرحله 1: پیدا کردن فایل
```bash
# پیدا کردن فایل تنظیمات
sudo grep -r "bi.cfu.ac.ir" /etc/nginx/
```

خروجی چیزی شبیه این خواهد بود:
```
/etc/nginx/sites-available/bi:    server_name bi.cfu.ac.ir;
```

### مرحله 2: ویرایش فایل
```bash
# ویرایش فایل (مثال)
sudo nano /etc/nginx/sites-available/bi
```

### مرحله 3: اضافه کردن تنظیمات
در بخش `server` مربوط به `bi.cfu.ac.ir`، این خط را اضافه کنید:
```nginx
client_max_body_size 50M;
```

### مرحله 4: بررسی و اعمال
```bash
# بررسی صحت تنظیمات
sudo nginx -t

# اعمال تغییرات
sudo systemctl reload nginx

# بررسی وضعیت
sudo systemctl status nginx
```

## مثال کامل فایل تنظیمات

```nginx
# /etc/nginx/sites-available/bi

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name bi.cfu.ac.ir;
    return 301 https://$server_name$request_uri;
}

# HTTPS Server
server {
    listen 443 ssl http2;
    server_name bi.cfu.ac.ir;

    # SSL certificates
    ssl_certificate /etc/ssl/certs/bi.cfu.ac.ir.crt;
    ssl_certificate_key /etc/ssl/private/bi.cfu.ac.ir.key;

    # ⭐ این خط را اضافه کنید:
    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # ⭐ این خطوط را نیز اضافه کنید:
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

## اولویت تنظیمات

اگر `client_max_body_size` در چند جا تعریف شده باشد، اولویت به این ترتیب است:

1. **`location`** (بالاترین اولویت)
2. **`server`** (اولویت متوسط)
3. **`http`** (اولویت پایین‌تر)

**توصیه:** در بخش `server` مربوط به سایت خود تنظیم کنید.

## بررسی تنظیمات اعمال شده

```bash
# بررسی مقدار فعلی
sudo nginx -T | grep client_max_body_size

# بررسی تنظیمات کامل
sudo nginx -T | grep -A 5 "server_name bi.cfu.ac.ir"
```

## نکات مهم

1. **بعد از تغییر فایل، حتماً `nginx -t` را اجرا کنید** تا از صحت تنظیمات اطمینان حاصل کنید
2. **بعد از `nginx -t` موفق، `reload` یا `restart` کنید**
3. **اگر فایل در `sites-available` است، مطمئن شوید که در `sites-enabled` لینک شده است:**
   ```bash
   sudo ln -s /etc/nginx/sites-available/bi /etc/nginx/sites-enabled/
   ```

## خلاصه

**فایل اصلی:** `/etc/nginx/sites-available/bi` (یا نام مشابه)  
**مکان تنظیمات:** در بخش `server` مربوط به `bi.cfu.ac.ir`  
**خط مورد نیاز:** `client_max_body_size 50M;`

