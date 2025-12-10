#!/bin/bash

# اسکریپت رفع خطای 413 Request Entity Too Large در Nginx
# این اسکریپت تنظیمات nginx را برای پشتیبانی از آپلود فایل‌های تا 50MB تنظیم می‌کند

echo "=========================================="
echo "رفع خطای 413 Request Entity Too Large"
echo "=========================================="
echo ""

# بررسی دسترسی root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ این اسکریپت نیاز به دسترسی root دارد. لطفاً با sudo اجرا کنید:"
    echo "   sudo bash fix_nginx_413.sh"
    exit 1
fi

# پیدا کردن فایل تنظیمات nginx
echo "🔍 در حال جستجوی فایل تنظیمات nginx..."

NGINX_CONFIG=""
POSSIBLE_CONFIGS=(
    "/etc/nginx/sites-available/bi"
    "/etc/nginx/sites-available/bi.cfu.ac.ir"
    "/etc/nginx/sites-enabled/bi"
    "/etc/nginx/sites-enabled/bi.cfu.ac.ir"
    "/etc/nginx/nginx.conf"
    "/etc/nginx/conf.d/default.conf"
)

for config in "${POSSIBLE_CONFIGS[@]}"; do
    if [ -f "$config" ]; then
        # بررسی اینکه آیا این فایل مربوط به bi.cfu.ac.ir است
        if grep -q "bi.cfu.ac.ir" "$config" 2>/dev/null; then
            NGINX_CONFIG="$config"
            echo "✅ فایل تنظیمات پیدا شد: $NGINX_CONFIG"
            break
        fi
    fi
done

# اگر فایل پیدا نشد، از کاربر بپرسید
if [ -z "$NGINX_CONFIG" ]; then
    echo "⚠️  فایل تنظیمات به صورت خودکار پیدا نشد."
    echo "لطفاً مسیر فایل تنظیمات nginx را وارد کنید:"
    read -p "مسیر فایل: " NGINX_CONFIG
    
    if [ ! -f "$NGINX_CONFIG" ]; then
        echo "❌ فایل پیدا نشد: $NGINX_CONFIG"
        exit 1
    fi
fi

# پشتیبان‌گیری از فایل
BACKUP_FILE="${NGINX_CONFIG}.backup.$(date +%Y%m%d_%H%M%S)"
echo ""
echo "📦 در حال ایجاد پشتیبان از فایل تنظیمات..."
cp "$NGINX_CONFIG" "$BACKUP_FILE"
echo "✅ پشتیبان ایجاد شد: $BACKUP_FILE"

# بررسی تنظیمات فعلی
echo ""
echo "🔍 بررسی تنظیمات فعلی..."
CURRENT_SIZE=$(grep -i "client_max_body_size" "$NGINX_CONFIG" | head -1 | awk '{print $2}' | tr -d ';' || echo "not found")

if [ "$CURRENT_SIZE" != "not found" ]; then
    echo "   مقدار فعلی: client_max_body_size $CURRENT_SIZE"
else
    echo "   مقدار فعلی: تنظیم نشده (پیش‌فرض: 1M)"
fi

# ویرایش فایل
echo ""
echo "✏️  در حال اعمال تغییرات..."

# بررسی اینکه آیا تنظیمات در بخش server وجود دارد
if grep -q "server_name.*bi.cfu.ac.ir" "$NGINX_CONFIG"; then
    # اگر در بخش server است، تنظیمات را اضافه یا تغییر می‌دهیم
    if grep -q "client_max_body_size" "$NGINX_CONFIG"; then
        # اگر وجود دارد، تغییر می‌دهیم
        sed -i 's/client_max_body_size.*/client_max_body_size 50M;/g' "$NGINX_CONFIG"
        echo "✅ مقدار client_max_body_size به 50M تغییر یافت"
    else
        # اگر وجود ندارد، بعد از server_name اضافه می‌کنیم
        sed -i '/server_name.*bi.cfu.ac.ir/a\    client_max_body_size 50M;' "$NGINX_CONFIG"
        echo "✅ client_max_body_size 50M اضافه شد"
    fi
    
    # بررسی و اضافه کردن timeout‌ها
    if ! grep -q "proxy_read_timeout" "$NGINX_CONFIG"; then
        # پیدا کردن location / و اضافه کردن timeout‌ها
        if grep -q "location /" "$NGINX_CONFIG"; then
            sed -i '/location \/ {/a\        proxy_read_timeout 300s;\n        proxy_connect_timeout 300s;\n        proxy_send_timeout 300s;' "$NGINX_CONFIG"
            echo "✅ timeout‌ها اضافه شدند"
        fi
    else
        # اگر وجود دارد، به‌روزرسانی می‌کنیم
        sed -i 's/proxy_read_timeout.*/proxy_read_timeout 300s;/g' "$NGINX_CONFIG"
        sed -i 's/proxy_connect_timeout.*/proxy_connect_timeout 300s;/g' "$NGINX_CONFIG"
        sed -i 's/proxy_send_timeout.*/proxy_send_timeout 300s;/g' "$NGINX_CONFIG"
        echo "✅ timeout‌ها به‌روزرسانی شدند"
    fi
else
    echo "⚠️  بخش server برای bi.cfu.ac.ir پیدا نشد."
    echo "لطفاً به صورت دستی تنظیمات را اضافه کنید."
    echo ""
    echo "مثال:"
    echo "server {"
    echo "    server_name bi.cfu.ac.ir;"
    echo "    client_max_body_size 50M;"
    echo "    ..."
    echo "}"
    exit 1
fi

# بررسی صحت تنظیمات
echo ""
echo "🔍 بررسی صحت تنظیمات nginx..."
if nginx -t 2>/dev/null; then
    echo "✅ تنظیمات صحیح است"
else
    echo "❌ خطا در تنظیمات nginx!"
    echo "در حال بازگردانی پشتیبان..."
    cp "$BACKUP_FILE" "$NGINX_CONFIG"
    echo "✅ فایل بازگردانی شد"
    exit 1
fi

# اعمال تغییرات
echo ""
echo "🔄 در حال اعمال تغییرات..."
if systemctl reload nginx 2>/dev/null; then
    echo "✅ Nginx با موفقیت reload شد"
elif systemctl restart nginx 2>/dev/null; then
    echo "✅ Nginx با موفقیت restart شد"
else
    echo "⚠️  خطا در reload/restart nginx. لطفاً به صورت دستی انجام دهید:"
    echo "   sudo systemctl reload nginx"
    exit 1
fi

# بررسی وضعیت
echo ""
echo "📊 بررسی وضعیت nginx..."
systemctl status nginx --no-pager -l | head -10

echo ""
echo "=========================================="
echo "✅ تنظیمات با موفقیت اعمال شد!"
echo "=========================================="
echo ""
echo "تنظیمات اعمال شده:"
echo "  - client_max_body_size: 50M"
echo "  - proxy_read_timeout: 300s"
echo "  - proxy_connect_timeout: 300s"
echo "  - proxy_send_timeout: 300s"
echo ""
echo "پشتیبان فایل: $BACKUP_FILE"
echo ""
echo "برای بررسی تنظیمات:"
echo "  sudo grep -r 'client_max_body_size' /etc/nginx/"
echo ""

