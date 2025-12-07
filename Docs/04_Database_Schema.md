# طرح دیتابیس

## 📋 فهرست مطالب

1. [دیتابیس access_control.db](#دیتابیس-access_controldb)
2. [دیتابیس faculty_data.db](#دیتابیس-faculty_datadb)
3. [روابط بین جداول](#روابط-بین-جداول)
4. [Index ها](#index-ها)
5. [مایگریشن‌ها](#مایگریشن‌ها)

---

## دیتابیس access_control.db

این دیتابیس شامل اطلاعات کاربران، پروژه‌ها، تسک‌ها، و تنظیمات سیستم است.

### جدول users

**توضیحات**: اطلاعات کاربران سیستم

| ستون | نوع | محدودیت | توضیحات |
|------|-----|---------|---------|
| id | INTEGER | PRIMARY KEY | شناسه یکتا |
| name | VARCHAR | NOT NULL | نام کاربر |
| email | VARCHAR | UNIQUE | ایمیل کاربر |
| sso_id | VARCHAR | NOT NULL | شناسه SSO |
| province_code | INTEGER | NULL | کد استان |
| university_code | INTEGER | NULL | کد دانشگاه |
| faculty_code | INTEGER | NULL | کد دانشکده |

**Index ها**:
- `idx_users_sso_id` روی `sso_id`
- `idx_users_province_code` روی `province_code`
- `idx_users_faculty_code` روی `faculty_code`

### جدول access_levels

**توضیحات**: سطوح دسترسی کاربران

| ستون | نوع | محدودیت | توضیحات |
|------|-----|---------|---------|
| id | INTEGER | PRIMARY KEY | شناسه یکتا |
| user_id | INTEGER | FOREIGN KEY → users.id | شناسه کاربر |
| level | VARCHAR(100) | NOT NULL | سطح دسترسی (admin, central_org, province_university, faculty) |

**Index ها**:
- `idx_access_levels_user_id` روی `user_id`

### جدول projects

**توضیحات**: پروژه‌های سیستم Kanban

| ستون | نوع | محدودیت | توضیحات |
|------|-----|---------|---------|
| id | INTEGER | PRIMARY KEY | شناسه یکتا |
| title | VARCHAR | NULL | عنوان پروژه |
| name | VARCHAR | NULL | نام پروژه |
| description | TEXT | NULL | توضیحات |
| start_date | DATE | NULL | تاریخ شروع |
| end_date | DATE | NULL | تاریخ پایان |
| creator_id | INTEGER | FOREIGN KEY → users.id | شناسه سازنده |
| owner_id | INTEGER | FOREIGN KEY → users.id | شناسه مالک |
| sso_id | VARCHAR | NULL | شناسه SSO |
| attachment | VARCHAR | NULL | فایل پیوست |
| updated_at | DATETIME | NULL | تاریخ به‌روزرسانی |

**Index ها**:
- `idx_projects_creator_id` روی `creator_id`
- `idx_projects_owner_id` روی `owner_id`

### جدول project_members

**توضیحات**: جدول ارتباطی برای اعضای پروژه (Many-to-Many)

| ستون | نوع | محدودیت | توضیحات |
|------|-----|---------|---------|
| user_id | INTEGER | PRIMARY KEY, FOREIGN KEY → users.id | شناسه کاربر |
| project_id | INTEGER | PRIMARY KEY, FOREIGN KEY → projects.id | شناسه پروژه |

### جدول kanban_columns

**توضیحات**: ستون‌های Kanban برای هر پروژه

| ستون | نوع | محدودیت | توضیحات |
|------|-----|---------|---------|
| id | INTEGER | PRIMARY KEY | شناسه یکتا |
| project_id | INTEGER | FOREIGN KEY → projects.id, NOT NULL | شناسه پروژه |
| title | VARCHAR(255) | NOT NULL | عنوان ستون |
| order | INTEGER | NOT NULL | ترتیب نمایش |
| position | INTEGER | NULL | موقعیت (برای drag & drop) |

**Index ها**:
- `idx_kanban_columns_project_id` روی `project_id`
- `idx_kanban_columns_order` روی `order`

### جدول kanban_column_users

**توضیحات**: جدول ارتباطی برای کاربران ستون‌های Kanban (Many-to-Many)

| ستون | نوع | محدودیت | توضیحات |
|------|-----|---------|---------|
| column_id | INTEGER | PRIMARY KEY, FOREIGN KEY → kanban_columns.id | شناسه ستون |
| user_id | INTEGER | PRIMARY KEY, FOREIGN KEY → users.id | شناسه کاربر |

### جدول tasks

**توضیحات**: تسک‌های سیستم Kanban

| ستون | نوع | محدودیت | توضیحات |
|------|-----|---------|---------|
| id | INTEGER | PRIMARY KEY | شناسه یکتا |
| column_id | INTEGER | FOREIGN KEY → kanban_columns.id, NOT NULL | شناسه ستون |
| project_id | INTEGER | FOREIGN KEY → projects.id | شناسه پروژه |
| title | VARCHAR(255) | NOT NULL | عنوان تسک |
| description | TEXT | NULL | توضیحات |
| due_date | TEXT | NULL | تاریخ سررسید |
| start_date | TEXT | NULL | تاریخ شروع |
| assignee_id | INTEGER | FOREIGN KEY → users.id | شناسه مسئول |

**Index ها**:
- `idx_tasks_column_id` روی `column_id`
- `idx_tasks_project_id` روی `project_id`
- `idx_tasks_assignee_id` روی `assignee_id`

### جدول task_assigned_users

**توضیحات**: جدول ارتباطی برای کاربران اختصاص داده شده به تسک‌ها (Many-to-Many)

| ستون | نوع | محدودیت | توضیحات |
|------|-----|---------|---------|
| task_id | INTEGER | PRIMARY KEY, FOREIGN KEY → tasks.id | شناسه تسک |
| user_id | INTEGER | PRIMARY KEY, FOREIGN KEY → users.id | شناسه کاربر |

### جدول labels

**توضیحات**: برچسب‌های پروژه

| ستون | نوع | محدودیت | توضیحات |
|------|-----|---------|---------|
| id | INTEGER | PRIMARY KEY | شناسه یکتا |
| name | VARCHAR(100) | NOT NULL | نام برچسب |
| project_id | INTEGER | FOREIGN KEY → projects.id | شناسه پروژه (NULL = عمومی) |

**Index ها**:
- `idx_labels_project_id` روی `project_id`

### جدول label_values

**توضیحات**: مقادیر برچسب‌ها

| ستون | نوع | محدودیت | توضیحات |
|------|-----|---------|---------|
| id | INTEGER | PRIMARY KEY | شناسه یکتا |
| label_id | INTEGER | FOREIGN KEY → labels.id, NOT NULL | شناسه برچسب |
| value | VARCHAR(100) | NOT NULL | مقدار برچسب |

**Unique Constraint**: `(label_id, value)`

### جدول task_label_assignments

**توضیحات**: اختصاص برچسب‌ها به تسک‌ها

| ستون | نوع | محدودیت | توضیحات |
|------|-----|---------|---------|
| id | INTEGER | PRIMARY KEY | شناسه یکتا |
| task_id | INTEGER | FOREIGN KEY → tasks.id, NOT NULL | شناسه تسک |
| label_id | INTEGER | FOREIGN KEY → labels.id, NOT NULL | شناسه برچسب |
| label_value_id | INTEGER | FOREIGN KEY → label_values.id, NOT NULL | شناسه مقدار برچسب |

**Unique Constraint**: `(task_id, label_id)`

### جدول reports

**توضیحات**: گزارش‌های تسک‌ها

| ستون | نوع | محدودیت | توضیحات |
|------|-----|---------|---------|
| id | INTEGER | PRIMARY KEY | شناسه یکتا |
| task_id | INTEGER | FOREIGN KEY → tasks.id, NOT NULL | شناسه تسک |
| user_id | INTEGER | FOREIGN KEY → users.id, NOT NULL | شناسه کاربر |
| text | TEXT | NOT NULL | متن گزارش |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | تاریخ ایجاد |

**Index ها**:
- `idx_reports_task_id` روی `task_id`
- `idx_reports_user_id` روی `user_id`

---

## جداول پنل ادمین

### جدول dashboard_access

**توضیحات**: دسترسی کاربران به داشبوردها

| ستون | نوع | محدودیت | توضیحات |
|------|-----|---------|---------|
| id | INTEGER | PRIMARY KEY | شناسه یکتا |
| user_id | INTEGER | FOREIGN KEY → users.id, NOT NULL | شناسه کاربر |
| dashboard_id | VARCHAR(100) | NOT NULL | شناسه داشبورد |
| can_access | BOOLEAN | DEFAULT TRUE, NOT NULL | آیا دسترسی دارد |
| filter_restrictions | JSON | NULL | محدودیت‌های فیلتر (JSON) |
| date_from | DATETIME | NULL | تاریخ شروع دسترسی |
| date_to | DATETIME | NULL | تاریخ پایان دسترسی |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | تاریخ ایجاد |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | تاریخ به‌روزرسانی |
| created_by | INTEGER | FOREIGN KEY → users.id | شناسه سازنده |

**Index ها**:
- `idx_dashboard_access_user_id` روی `user_id`
- `idx_dashboard_access_dashboard_id` روی `dashboard_id`

### جدول access_logs

**توضیحات**: لاگ دسترسی کاربران

| ستون | نوع | محدودیت | توضیحات |
|------|-----|---------|---------|
| id | INTEGER | PRIMARY KEY | شناسه یکتا |
| user_id | INTEGER | FOREIGN KEY → users.id, NOT NULL | شناسه کاربر |
| action | VARCHAR(100) | NOT NULL | نوع عمل |
| resource_type | VARCHAR(50) | NULL | نوع منبع |
| resource_id | VARCHAR(100) | NULL | شناسه منبع |
| ip_address | VARCHAR(45) | NULL | آدرس IP |
| user_agent | TEXT | NULL | User Agent |
| request_path | VARCHAR(500) | NULL | مسیر درخواست |
| request_method | VARCHAR(10) | NULL | متد HTTP |
| details | JSON | NULL | جزئیات اضافی (JSON) |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | تاریخ ایجاد |

**Index ها**:
- `idx_access_logs_user_id` روی `user_id`
- `idx_access_logs_action` روی `action`
- `idx_access_logs_created_at` روی `created_at`

### جدول data_syncs

**توضیحات**: تنظیمات و وضعیت همگام‌سازی داده‌ها

| ستون | نوع | محدودیت | توضیحات |
|------|-----|---------|---------|
| id | INTEGER | PRIMARY KEY | شناسه یکتا |
| data_source | VARCHAR(100) | UNIQUE, NOT NULL | منبع داده (faculty, students, lms) |
| sync_type | VARCHAR(50) | NOT NULL | نوع همگام‌سازی (auto, manual, scheduled) |
| status | VARCHAR(50) | DEFAULT 'pending', NOT NULL | وضعیت (pending, running, success, failed) |
| last_sync_at | DATETIME | NULL | تاریخ آخرین همگام‌سازی |
| next_sync_at | DATETIME | NULL | تاریخ همگام‌سازی بعدی |
| auto_sync_enabled | BOOLEAN | DEFAULT TRUE, NOT NULL | آیا همگام‌سازی خودکار فعال است |
| sync_interval_value | INTEGER | DEFAULT 60, NOT NULL | مقدار بازه زمانی |
| sync_interval_unit | VARCHAR(20) | DEFAULT 'minutes', NOT NULL | واحد بازه زمانی (minutes, hours, days) |
| api_base_url | VARCHAR(500) | NULL | آدرس پایه API |
| api_endpoint | VARCHAR(500) | NULL | آدرس کامل endpoint |
| api_method | VARCHAR(10) | DEFAULT 'GET', NOT NULL | متد HTTP |
| api_username | VARCHAR(200) | NULL | نام کاربری API |
| api_password | VARCHAR(500) | NULL | رمز عبور API |
| api_params | JSON | NULL | پارامترهای API (JSON) |
| records_synced | INTEGER | DEFAULT 0, NOT NULL | تعداد رکوردهای همگام‌سازی شده |
| sync_duration_seconds | FLOAT | NULL | مدت زمان همگام‌سازی (ثانیه) |
| error_message | TEXT | NULL | پیام خطا |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | تاریخ ایجاد |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | تاریخ به‌روزرسانی |
| last_synced_by | INTEGER | FOREIGN KEY → users.id | شناسه کاربر همگام‌سازی کننده |

**Index ها**:
- `idx_data_syncs_data_source` روی `data_source`
- `idx_data_syncs_status` روی `status`

### جدول dashboard_configs

**توضیحات**: تنظیمات داشبوردها

| ستون | نوع | محدودیت | توضیحات |
|------|-----|---------|---------|
| id | INTEGER | PRIMARY KEY | شناسه یکتا |
| dashboard_id | VARCHAR(100) | UNIQUE, NOT NULL | شناسه داشبورد |
| title | VARCHAR(200) | NOT NULL | عنوان |
| description | TEXT | NULL | توضیحات |
| icon | VARCHAR(100) | NULL | آیکون |
| order | INTEGER | DEFAULT 0, NOT NULL | ترتیب نمایش |
| is_active | BOOLEAN | DEFAULT TRUE, NOT NULL | آیا فعال است |
| is_public | BOOLEAN | DEFAULT FALSE, NOT NULL | آیا عمومی است |
| cache_ttl_seconds | INTEGER | DEFAULT 300, NOT NULL | زمان Cache (ثانیه) |
| refresh_interval_seconds | INTEGER | NULL | بازه به‌روزرسانی خودکار (ثانیه) |
| config | JSON | NULL | تنظیمات سفارشی (JSON) |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | تاریخ ایجاد |
| updated_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | تاریخ به‌روزرسانی |
| created_by | INTEGER | FOREIGN KEY → users.id | شناسه سازنده |

**Index ها**:
- `idx_dashboard_configs_dashboard_id` روی `dashboard_id`

---

## دیتابیس faculty_data.db

این دیتابیس شامل داده‌های دانشکده‌ها، دانشجویان، و پایش LMS است.

### جدول faculty

**توضیحات**: اطلاعات دانشکده‌ها

| ستون | نوع | محدودیت | توضیحات |
|------|-----|---------|---------|
| id | INTEGER | PRIMARY KEY | شناسه یکتا |
| code_markaz | INTEGER | UNIQUE | کد مرکز (دانشکده) |
| name | VARCHAR | NULL | نام دانشکده |
| province_code | INTEGER | NULL | کد استان |
| university_code | INTEGER | NULL | کد دانشگاه |
| ... | ... | ... | سایر فیلدها |

**Index ها**:
- `idx_faculty_code_markaz` روی `code_markaz`
- `idx_faculty_province_code` روی `province_code`

### جدول students

**توضیحات**: اطلاعات دانشجویان

| ستون | نوع | محدودیت | توضیحات |
|------|-----|---------|---------|
| id | INTEGER | PRIMARY KEY | شناسه یکتا |
| student_id | VARCHAR | UNIQUE | شماره دانشجویی |
| name | VARCHAR | NULL | نام دانشجو |
| faculty_code | INTEGER | NULL | کد دانشکده |
| ... | ... | ... | سایر فیلدها |

**Index ها**:
- `idx_students_student_id` روی `student_id`
- `idx_students_faculty_code` روی `faculty_code`

### جدول monitor_data

**توضیحات**: داده‌های پایش LMS

| ستون | نوع | محدودیت | توضیحات |
|------|-----|---------|---------|
| id | INTEGER | PRIMARY KEY | شناسه یکتا |
| url | VARCHAR | NOT NULL | URL منبع |
| timestamp | DATETIME | NOT NULL | زمان ثبت |
| key | VARCHAR | NOT NULL | کلید داده |
| value | INTEGER | NOT NULL | مقدار |

**Index ها**:
- `idx_monitor_data_url` روی `url`
- `idx_monitor_data_timestamp` روی `timestamp`
- `idx_monitor_data_key` روی `key`
- `idx_monitor_data_url_timestamp` روی `(url, timestamp)`

---

## روابط بین جداول

### نمودار ER (ساده‌شده)

```
users
  ├── access_levels (1:N)
  ├── projects (1:N) [creator]
  ├── projects (1:N) [owner]
  ├── project_members (N:M)
  ├── kanban_column_users (N:M)
  ├── task_assigned_users (N:M)
  ├── dashboard_access (1:N)
  ├── access_logs (1:N)
  └── data_syncs (1:N) [last_synced_by]

projects
  ├── project_members (N:M)
  ├── kanban_columns (1:N)
  └── labels (1:N)

kanban_columns
  ├── kanban_column_users (N:M)
  └── tasks (1:N)

tasks
  ├── task_assigned_users (N:M)
  ├── task_label_assignments (1:N)
  └── reports (1:N)

labels
  ├── label_values (1:N)
  └── task_label_assignments (1:N)

label_values
  └── task_label_assignments (1:N)
```

---

## Index ها

### Index های مهم برای Performance

1. **users**:
   - `sso_id`: برای جستجوی سریع کاربر
   - `province_code`, `faculty_code`: برای فیلتر سریع

2. **tasks**:
   - `column_id`: برای نمایش تسک‌های یک ستون
   - `project_id`: برای نمایش تسک‌های یک پروژه

3. **monitor_data**:
   - `(url, timestamp)`: برای Query های زمانی
   - `key`: برای فیلتر بر اساس نوع داده

4. **access_logs**:
   - `created_at`: برای Query های زمانی
   - `user_id, action`: برای فیلتر لاگ‌ها

---

## مایگریشن‌ها

### مایگریشن‌های موجود

1. **add_user_org_fields.py**: اضافه کردن فیلدهای سازمانی به User
2. **add_api_credentials_to_sync.py**: اضافه کردن فیلدهای احراز هویت API
3. **add_sync_interval_unit.py**: اضافه کردن فیلدهای بازه زمانی همگام‌سازی
4. **create_admin_tables.py**: ایجاد جداول پنل ادمین
5. **fix_duplicate_syncs.py**: رفع مشکل همگام‌سازی‌های تکراری

### نحوه اجرای مایگریشن

```python
# در Flask shell یا script
from app import app, db
from app.migrations.add_user_org_fields import add_user_org_fields

with app.app_context():
    add_user_org_fields()
```

---

## Backup و Restore

### Backup

```bash
# Backup access_control.db
sqlite3 app/access_control.db ".backup backup_access_control.db"

# Backup faculty_data.db
sqlite3 app/fetch_data/faculty_data.db ".backup backup_faculty_data.db"
```

### Restore

```bash
# Restore access_control.db
sqlite3 app/access_control.db ".restore backup_access_control.db"

# Restore faculty_data.db
sqlite3 app/fetch_data/faculty_data.db ".restore backup_faculty_data.db"
```

---

**تاریخ ایجاد**: 1404/01/XX  
**آخرین به‌روزرسانی**: 1404/01/XX
