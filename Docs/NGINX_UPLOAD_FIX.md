# راهنمای رفع خطای 413 Request Entity Too Large در Nginx

## مشکل
خطای `413 Request Entity Too Large` زمانی رخ می‌دهد که حجم فایل آپلود شده بیشتر از محدودیت تعریف شده در Nginx باشد.

## راه حل

### 1. تنظیم Nginx

فایل تنظیمات Nginx را ویرایش کنید (معمولاً در `/etc/nginx/nginx.conf` یا `/etc/nginx/sites-available/your-site`):

```nginx
http {
    # ...
    
    # افزایش محدودیت برای آپلود فایل
    client_max_body_size 5M;  # 5 مگابایت (یا بیشتر اگر نیاز دارید)
    
    server {
        # ...
        
        # یا می‌توانید برای یک location خاص تنظیم کنید:
        location /survey/ {
            client_max_body_size 5M;
        }
    }
}
```

### 2. ری‌استارت Nginx

بعد از تغییر تنظیمات:

```bash
# تست تنظیمات
sudo nginx -t

# ری‌استارت Nginx
sudo systemctl restart nginx
# یا
sudo service nginx restart
```

### 3. محدودیت در کد

در کد Flask، محدودیت آپلود لوگو به **2 مگابایت** تنظیم شده است. این برای تصاویر لوگو کافی است.

اگر نیاز به آپلود فایل‌های بزرگ‌تر دارید:
- محدودیت Nginx را افزایش دهید
- محدودیت در `app/survey/utils.py` را نیز افزایش دهید

## توصیه

برای لوگوهای نظرسنجی:
- **حداکثر 2 مگابایت** کافی است
- فرمت‌های توصیه شده: PNG یا JPG
- قبل از آپلود، تصویر را فشرده کنید

## بررسی تنظیمات فعلی

برای بررسی تنظیمات فعلی Nginx:

```bash
grep -r "client_max_body_size" /etc/nginx/
```

