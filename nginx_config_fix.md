# راهنمای رفع خطای 413 Request Entity Too Large

## مشکل
خطای 413 زمانی رخ می‌دهد که اندازه درخواست (request body) از حد مجاز nginx بیشتر باشد. این مشکل معمولاً هنگام آپلود فایل‌های بزرگ رخ می‌دهد.

## راه حل

### 1. افزایش `client_max_body_size` در Nginx

فایل تنظیمات nginx را ویرایش کنید (معمولاً در `/etc/nginx/sites-available/bi` یا `/etc/nginx/nginx.conf`):

```nginx
server {
    listen 443 ssl http2;
    server_name bi.cfu.ac.ir;

    # افزایش حد مجاز اندازه درخواست به 50M (برای پشتیبانی از فایل‌های تا 50 مگابایت)
    client_max_body_size 50M;
    
    # یا برای فایل‌های بزرگ‌تر:
    # client_max_body_size 100M;

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

### 2. اعمال تغییرات

```bash
# بررسی صحت تنظیمات
sudo nginx -t

# بارگذاری مجدد nginx
sudo systemctl reload nginx
```

### 3. بررسی تنظیمات فعلی

برای بررسی مقدار فعلی `client_max_body_size`:

```bash
# جستجوی تنظیمات فعلی
sudo grep -r "client_max_body_size" /etc/nginx/
```

### 4. تنظیمات پیشنهادی

با توجه به اینکه حداکثر حجم فایل در پرسشنامه‌ها 50 مگابایت است، پیشنهاد می‌شود:

- `client_max_body_size 50M;` - برای پشتیبانی از فایل‌های تا 50 مگابایت
- `proxy_read_timeout 300s;` - برای آپلود فایل‌های بزرگ
- `proxy_connect_timeout 300s;` - برای اتصال
- `proxy_send_timeout 300s;` - برای ارسال

### 5. نکات مهم

- اگر `client_max_body_size` در سطح `http` تنظیم شده باشد، نیازی به تنظیم مجدد در `server` نیست
- مقدار پیش‌فرض nginx معمولاً 1M است که برای آپلود فایل کافی نیست
- بعد از تغییر تنظیمات، حتماً nginx را reload کنید

