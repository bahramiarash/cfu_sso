# مستندات API - سامانه BI دانشگاه فرهنگیان

## 1. مقدمه

این سند شامل مستندات کامل API های سامانه BI دانشگاه فرهنگیان است. API ها به دو دسته اصلی تقسیم می‌شوند:
- **Dashboard API**: برای دسترسی به داده‌های داشبوردها
- **Admin API**: برای مدیریت سیستم

## 2. احراز هویت

### 2.1 SSO Authentication

تمام API ها نیاز به احراز هویت دارند. احراز هویت از طریق SSO انجام می‌شود.

**Flow**:
1. کاربر به `/login` می‌رود
2. سیستم به SSO Redirect می‌کند
3. پس از احراز هویت، SSO به `/authorized` Redirect می‌کند
4. Session ایجاد می‌شود

**Headers مورد نیاز**:
```
Cookie: session=<session_id>
```

## 3. Dashboard API

### 3.1 لیست داشبوردها

**Endpoint**: `GET /dashboards/`

**توضیحات**: لیست داشبوردهای قابل دسترسی برای کاربر فعلی

**Authentication**: ✅ Required

**Response**:
```json
{
  "dashboards": [
    {
      "dashboard_id": "d1",
      "dashboard_title": "📊 آمار اعضای هیئت علمی",
      "dashboard_description": "آمار تفصیلی اعضای هیئت علمی"
    },
    {
      "dashboard_id": "students",
      "dashboard_title": "📊 داشبورد اطلاعات دانشجو معلمان",
      "dashboard_description": "آمار تفصیلی دانشجو معلمان"
    }
  ]
}
```

**Status Codes**:
- `200 OK`: موفق
- `401 Unauthorized`: نیاز به احراز هویت
- `500 Internal Server Error`: خطای سرور

---

### 3.2 نمایش داشبورد

**Endpoint**: `GET /dashboards/<dashboard_id>`

**توضیحات**: نمایش داشبورد خاص با فیلترهای اختیاری

**Authentication**: ✅ Required

**Parameters** (Query String):
- `province_code` (optional): کد استان
- `university_code` (optional): کد دانشگاه
- `faculty_code` (optional): کد دانشکده
- `date_from` (optional): تاریخ شروع (فرمت: YYYY/MM/DD)
- `date_to` (optional): تاریخ پایان (فرمت: YYYY/MM/DD)

**Example**:
```
GET /dashboards/d1?province_code=1&faculty_code=100
```

**Response**: HTML Template

**Status Codes**:
- `200 OK`: موفق
- `403 Forbidden`: عدم دسترسی
- `404 Not Found`: داشبورد یافت نشد
- `500 Internal Server Error`: خطای سرور

---

### 3.3 Dashboard Filter API

**Endpoint**: `GET /api/dashboards/filters`

**توضیحات**: دریافت فیلترهای قابل استفاده برای کاربر

**Authentication**: ✅ Required

**Response**:
```json
{
  "can_filter_by_province": true,
  "can_filter_by_university": true,
  "can_filter_by_faculty": true,
  "available_provinces": [1, 2, 3],
  "available_faculties": [100, 101, 102]
}
```

**Status Codes**:
- `200 OK`: موفق
- `401 Unauthorized`: نیاز به احراز هویت

---

## 4. Admin API

### 4.1 لیست کاربران

**Endpoint**: `GET /admin/users`

**توضیحات**: لیست کاربران سیستم

**Authentication**: ✅ Required (Admin Only)

**Parameters** (Query String):
- `page` (optional): شماره صفحه (default: 1)
- `per_page` (optional): تعداد در هر صفحه (default: 20)
- `search` (optional): جستجو در نام، SSO ID یا ایمیل

**Example**:
```
GET /admin/users?page=1&per_page=20&search=test
```

**Response**: HTML Template

**Status Codes**:
- `200 OK`: موفق
- `401 Unauthorized`: نیاز به احراز هویت
- `403 Forbidden`: نیاز به دسترسی Admin

---

### 4.2 ایجاد کاربر

**Endpoint**: `POST /admin/users/new`

**Authentication**: ✅ Required (Admin Only)

**Request Body** (Form Data):
```
name: نام کاربر
sso_id: شناسه SSO
email: ایمیل (اختیاری)
province_code: کد استان (اختیاری)
university_code: کد دانشگاه (اختیاری)
faculty_code: کد دانشکده (اختیاری)
access_levels: لیست سطوح دسترسی (مثال: admin,central_org)
```

**Response**: Redirect to `/admin/users/<user_id>`

**Status Codes**:
- `302 Found`: Redirect
- `400 Bad Request`: داده‌های نامعتبر
- `401 Unauthorized`: نیاز به احراز هویت
- `403 Forbidden`: نیاز به دسترسی Admin

---

### 4.3 ویرایش کاربر

**Endpoint**: `POST /admin/users/<user_id>/edit`

**Authentication**: ✅ Required (Admin Only)

**Request Body** (Form Data):
```
name: نام کاربر
email: ایمیل
province_code: کد استان
university_code: کد دانشگاه
faculty_code: کد دانشکده
access_levels: لیست سطوح دسترسی
```

**Response**: Redirect to `/admin/users/<user_id>`

**Status Codes**:
- `302 Found`: Redirect
- `400 Bad Request`: داده‌های نامعتبر
- `404 Not Found`: کاربر یافت نشد

---

### 4.4 لیست همگام‌سازی‌ها

**Endpoint**: `GET /admin/data-sync`

**توضیحات**: لیست تنظیمات همگام‌سازی داده‌ها

**Authentication**: ✅ Required (Admin Only)

**Response**: HTML Template

**Status Codes**:
- `200 OK`: موفق
- `401 Unauthorized`: نیاز به احراز هویت
- `403 Forbidden`: نیاز به دسترسی Admin

---

### 4.5 همگام‌سازی دستی

**Endpoint**: `POST /admin/data-sync/<sync_id>/sync`

**توضیحات**: شروع همگام‌سازی دستی

**Authentication**: ✅ Required (Admin Only)

**Response**: Redirect to `/admin/data-sync`

**Status Codes**:
- `302 Found`: Redirect
- `404 Not Found`: همگام‌سازی یافت نشد

**Note**: برای LMS، همگام‌سازی مداوم متوقف می‌شود، همگام‌سازی دستی انجام می‌شود و سپس همگام‌سازی مداوم دوباره شروع می‌شود (اگر فعال باشد).

---

### 4.6 توقف همگام‌سازی

**Endpoint**: `POST /admin/data-sync/<sync_id>/stop`

**توضیحات**: توقف همگام‌سازی در حال اجرا

**Authentication**: ✅ Required (Admin Only)

**Response**: Redirect to `/admin/data-sync`

**Status Codes**:
- `302 Found`: Redirect
- `404 Not Found`: همگام‌سازی یافت نشد

---

### 4.7 ویرایش تنظیمات همگام‌سازی

**Endpoint**: `POST /admin/data-sync/<sync_id>/edit`

**Authentication**: ✅ Required (Admin Only)

**Request Body** (Form Data):
```
auto_sync_enabled: on/off
sync_interval_value: مقدار بازه زمانی (عدد)
sync_interval_unit: واحد بازه زمانی (minutes/hours/days)
api_base_url: آدرس پایه API
api_endpoint: آدرس کامل Endpoint
api_method: متد HTTP (GET/POST)
api_username: نام کاربری API
api_password: رمز عبور API (اختیاری - اگر خالی باشد، تغییر نمی‌کند)
```

**Response**: Redirect to `/admin/data-sync`

**Status Codes**:
- `302 Found`: Redirect
- `400 Bad Request`: داده‌های نامعتبر
- `404 Not Found`: همگام‌سازی یافت نشد

---

### 4.8 تست اتصال API

**Endpoint**: `POST /admin/data-sync/<sync_id>/test-connection`

**Authentication**: ✅ Required (Admin Only)

**Request Body** (Form Data - اختیاری):
```
api_base_url: آدرس پایه API (اگر خالی باشد، از تنظیمات استفاده می‌شود)
api_endpoint: آدرس کامل Endpoint (اگر خالی باشد، از تنظیمات استفاده می‌شود)
api_username: نام کاربری API (اگر خالی باشد، از تنظیمات استفاده می‌شود)
api_password: رمز عبور API (اگر خالی باشد، از تنظیمات استفاده می‌شود)
```

**Response** (JSON):
```json
{
  "success": true,
  "message": "اتصال موفق! Token دریافت شد و endpoint پاسخ داد. (Status: 200)"
}
```

یا در صورت خطا:
```json
{
  "success": false,
  "message": "خطا در اتصال: ..."
}
```

**Status Codes**:
- `200 OK`: موفق
- `400 Bad Request`: خطا در اتصال
- `404 Not Found`: همگام‌سازی یافت نشد

---

### 4.9 مشاهده پیشرفت همگام‌سازی

**Endpoint**: `GET /admin/data-sync/<sync_id>/progress`

**Authentication**: ✅ Required (Admin Only)

**Response** (JSON):
```json
{
  "status": "running",
  "progress": 45,
  "current_step": "Processing data",
  "records_processed": 450,
  "total_records": 1000,
  "error_message": null,
  "logs": [
    "Starting sync...",
    "Fetching data from API...",
    "Processing records..."
  ]
}
```

**Status Codes**:
- `200 OK`: موفق
- `404 Not Found`: همگام‌سازی یافت نشد

---

### 4.10 لیست لاگ‌ها

**Endpoint**: `GET /admin/logs`

**Authentication**: ✅ Required (Admin Only)

**Parameters** (Query String):
- `page` (optional): شماره صفحه (default: 1)
- `per_page` (optional): تعداد در هر صفحه (default: 50)
- `user_id` (optional): فیلتر بر اساس کاربر
- `action` (optional): فیلتر بر اساس نوع عمل

**Response**: HTML Template

**Status Codes**:
- `200 OK`: موفق
- `401 Unauthorized`: نیاز به احراز هویت
- `403 Forbidden`: نیاز به دسترسی Admin

---

## 5. Data API

### 5.1 Charts Data

**Endpoint**: `GET /charts-data`

**توضیحات**: دریافت داده‌های نمودار برای مانیتورینگ LMS

**Authentication**: ✅ Required

**Parameters** (Query String):
- `time_range` (optional): بازه زمانی (1h, 3h, 6h, 12h, 1d, 1w, 1m, 1y)
- `date_from` (optional): تاریخ شروع (فرمت: YYYY/MM/DD)
- `date_to` (optional): تاریخ پایان (فرمت: YYYY/MM/DD)
- `time_from` (optional): زمان شروع (فرمت: HH:MM, default: 00:00)
- `time_to` (optional): زمان پایان (فرمت: HH:MM, default: 23:59)

**Example**:
```
GET /charts-data?date_from=1403/01/01&date_to=1403/12/29
```

**Response** (JSON):
```json
{
  "Zone1": {
    "labels": ["1403/01/01 10:00", "1403/01/01 11:00", ...],
    "datasets": [
      {
        "label": "کاربران آنلاین LMS",
        "data": [150, 200, 180, ...],
        "borderColor": "#ff6384",
        "backgroundColor": "#ff6384",
        "fill": false
      }
    ],
    "title": "تهران و البرز"
  },
  "Zone2": { ... }
}
```

**Status Codes**:
- `200 OK`: موفق
- `401 Unauthorized`: نیاز به احراز هویت

---

### 5.2 Tables Data

**Endpoint**: `GET /tables-data`

**توضیحات**: دریافت داده‌های جدول برای مانیتورینگ LMS

**Authentication**: ✅ Required

**Response** (JSON):
```json
{
  "charts": {
    "Zone1": {
      "labels": [...],
      "datasets": [...],
      "latest_values": [
        {"online_lms_user": 150},
        {"online_adobe_class": 10}
      ],
      "latest_zone_resources": {
        "cpu": 45.2,
        "memory": 60.5,
        "disk": 30.1
      },
      "title": "تهران و البرز"
    }
  },
  "overall_sum": {
    "online_lms_user": 1500,
    "online_adobe_class": 100
  }
}
```

**Status Codes**:
- `200 OK`: موفق
- `401 Unauthorized`: نیاز به احراز هویت

---

### 5.3 همگام‌سازی دستی LMS

**Endpoint**: `GET /sync-lms-now`

**توضیحات**: شروع همگام‌سازی دستی LMS

**Authentication**: ✅ Required

**Response** (JSON):
```json
{
  "success": true,
  "message": "همگام‌سازی با موفقیت انجام شد. 1500 رکورد ثبت شد.",
  "records_count": 1500
}
```

یا در صورت خطا:
```json
{
  "success": false,
  "message": "خطا در همگام‌سازی داده‌ها"
}
```

**Status Codes**:
- `200 OK`: موفق
- `401 Unauthorized`: نیاز به احراز هویت
- `404 Not Found`: پیکربندی همگام‌سازی LMS یافت نشد
- `500 Internal Server Error`: خطا در همگام‌سازی

**Note**: این API همگام‌سازی مداوم را متوقف می‌کند، همگام‌سازی دستی را انجام می‌دهد و سپس همگام‌سازی مداوم را دوباره شروع می‌کند (اگر فعال باشد).

---

## 6. Error Handling

### 6.1 Error Response Format

```json
{
  "error": "Error message",
  "code": "ERROR_CODE",
  "details": {}
}
```

### 6.2 Status Codes

- `200 OK`: درخواست موفق
- `302 Found`: Redirect
- `400 Bad Request`: داده‌های نامعتبر
- `401 Unauthorized`: نیاز به احراز هویت
- `403 Forbidden`: عدم دسترسی
- `404 Not Found`: منبع یافت نشد
- `500 Internal Server Error`: خطای سرور

## 7. Rate Limiting

در حال حاضر Rate Limiting پیاده‌سازی نشده است. پیشنهاد می‌شود برای Production اضافه شود.

## 8. CORS

CORS برای API های عمومی پیکربندی نشده است. برای دسترسی خارجی نیاز به پیکربندی است.

## 9. نمونه استفاده

### 9.1 Python (requests)

```python
import requests

# Login (از طریق SSO)
session = requests.Session()
response = session.get('https://bi.cfu.ac.ir/login')

# Get Dashboard
response = session.get('https://bi.cfu.ac.ir/dashboards/d1?province_code=1')
print(response.text)

# Manual Sync
response = session.get('https://bi.cfu.ac.ir/sync-lms-now')
print(response.json())
```

### 9.2 JavaScript (fetch)

```javascript
// Get Dashboard
fetch('/dashboards/d1?province_code=1', {
  credentials: 'include'
})
.then(response => response.text())
.then(html => {
  // Process HTML
});

// Manual Sync
fetch('/sync-lms-now', {
  credentials: 'include'
})
.then(response => response.json())
.then(data => {
  console.log(data);
});
```

---

**تاریخ ایجاد**: 1404  
**آخرین به‌روزرسانی**: 1404

