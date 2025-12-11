#!/bin/bash

# اسکریپت رفع خطای 413 در صفحه ویرایش نظرسنجی
# این اسکریپت client_max_body_size را در nginx تنظیم می‌کند

echo "=========================================="
echo "رفع خطای 413 Request Entity Too Large"
echo "=========================================="
echo ""

# پیدا کردن فایل تنظیمات nginx
NGINX_CONFIG=""
POSSIBLE_PATHS=(
    "/etc/nginx/sites-available/bi"
    "/etc/nginx/sites-available/bi.cfu.ac.ir"
    "/etc/nginx/conf.d/default.conf"
    "/etc/nginx/nginx.conf"
)

echo "در حال جستجوی فایل تنظیمات nginx..."
for path in "${POSSIBLE_PATHS[@]}"; do
    if [ -f "$path" ] && grep -q "bi.cfu.ac.ir" "$path" 2>/dev/null; then
        NGINX_CONFIG="$path"
        echo "✅ فایل تنظیمات یافت شد: $NGINX_CONFIG"
        break
    fi
done

if [ -z "$NGINX_CONFIG" ]; then
    echo "❌ فایل تنظیمات nginx یافت نشد."
    echo "لطفاً به صورت دستی فایل تنظیمات را پیدا کنید:"
    echo "   sudo grep -r 'bi.cfu.ac.ir' /etc/nginx/"
    exit 1
fi

# بررسی مقدار فعلی
CURRENT_SIZE=$(grep -i "client_max_body_size" "$NGINX_CONFIG" | head -1 | awk '{print $2}' | tr -d ';' || echo "not found")

if [ "$CURRENT_SIZE" != "not found" ]; then
    echo "   مقدار فعلی: client_max_body_size $CURRENT_SIZE"
else
    echo "   مقدار فعلی: تنظیم نشده (پیش‌فرض: 1M)"
fi

echo ""
echo "در حال تنظیم client_max_body_size به 50M..."

# پشتیبان‌گیری از فایل
BACKUP_FILE="${NGINX_CONFIG}.backup.$(date +%Y%m%d_%H%M%S)"
sudo cp "$NGINX_CONFIG" "$BACKUP_FILE"
echo "✅ پشتیبان‌گیری ایجاد شد: $BACKUP_FILE"

# بررسی اینکه آیا تنظیمات در بخش server مربوط به bi.cfu.ac.ir وجود دارد
if grep -q "server_name.*bi.cfu.ac.ir" "$NGINX_CONFIG"; then
    # اگر تنظیمات وجود دارد، آن را به‌روزرسانی می‌کنیم
    if grep -q "client_max_body_size" "$NGINX_CONFIG"; then
        # به‌روزرسانی مقدار موجود
        sudo sed -i 's/client_max_body_size.*/client_max_body_size 50M;/g' "$NGINX_CONFIG"
        echo "✅ مقدار client_max_body_size به 50M تغییر یافت"
    else
        # اضافه کردن تنظیمات جدید بعد از server_name
        sudo sed -i '/server_name.*bi.cfu.ac.ir/a\    client_max_body_size 50M;' "$NGINX_CONFIG"
        echo "✅ client_max_body_size 50M اضافه شد"
    fi
else
    echo "⚠️  بخش server مربوط به bi.cfu.ac.ir یافت نشد."
    echo "لطفاً به صورت دستی تنظیمات را اضافه کنید."
    exit 1
fi

# اضافه کردن timeout settings اگر وجود نداشته باشند
if ! grep -q "proxy_read_timeout" "$NGINX_CONFIG"; then
    # پیدا کردن location / و اضافه کردن timeout
    if grep -q "location /" "$NGINX_CONFIG"; then
        sudo sed -i '/location \//a\        proxy_read_timeout 300s;\n        proxy_connect_timeout 300s;\n        proxy_send_timeout 300s;' "$NGINX_CONFIG"
        echo "✅ تنظیمات timeout اضافه شد"
    fi
fi

echo ""
echo "=========================================="
echo "بررسی صحت تنظیمات nginx..."
echo "=========================================="

# بررسی صحت تنظیمات
if sudo nginx -t 2>&1 | grep -q "syntax is ok"; then
    echo "✅ تنظیمات nginx صحیح است"
    echo ""
    echo "=========================================="
    echo "اعمال تغییرات..."
    echo "=========================================="
    
    # Reload nginx
    if sudo systemctl reload nginx 2>/dev/null; then
        echo "✅ Nginx با موفقیت reload شد"
    else
        echo "⚠️  Reload ناموفق بود، در حال restart..."
        sudo systemctl restart nginx
        if [ $? -eq 0 ]; then
            echo "✅ Nginx با موفقیت restart شد"
        else
            echo "❌ خطا در restart nginx"
            echo "لطفاً به صورت دستی بررسی کنید:"
            echo "   sudo systemctl status nginx"
            exit 1
        fi
    fi
    
    echo ""
    echo "=========================================="
    echo "✅ تغییرات با موفقیت اعمال شد!"
    echo "=========================================="
    echo ""
    echo "مقدار جدید client_max_body_size:"
    sudo grep "client_max_body_size" "$NGINX_CONFIG" | head -1
    echo ""
    echo "برای بررسی کامل:"
    echo "   sudo nginx -T | grep client_max_body_size"
    echo ""
else
    echo "❌ خطا در تنظیمات nginx!"
    echo "در حال بازگردانی پشتیبان..."
    sudo cp "$BACKUP_FILE" "$NGINX_CONFIG"
    echo "✅ پشتیبان بازگردانده شد"
    echo ""
    echo "لطفاً خطاهای زیر را بررسی کنید:"
    sudo nginx -t
    exit 1
fi

