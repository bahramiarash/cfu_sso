# سند معماری سیستم - سیستم BI دانشگاه

## 📐 معماری کلی

### نمای کلی معماری

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Layer (Browser)                    │
│  - HTML/CSS/JavaScript                                       │
│  - Bootstrap RTL                                             │
│  - Chart.js, Plotly                                         │
└─────────────────────────────────────────────────────────────┘
                            ↓ HTTPS
┌─────────────────────────────────────────────────────────────┐
│                  Application Server (Flask)                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Authentication Layer                                 │  │
│  │  - SSO Integration (OAuth2)                           │  │
│  │  - Session Management                                 │  │
│  │  - Access Control                                     │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Business Logic Layer                                │  │
│  │  - Dashboard System                                  │  │
│  │  - Admin Panel                                       │  │
│  │  - Project Management                                │  │
│  │  - Data Sync                                         │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Data Access Layer                                   │  │
│  │  - Data Providers                                    │  │
│  │  - ORM (SQLAlchemy)                                  │  │
│  │  - Cache System                                      │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    Data Layer                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ access_      │  │ faculty_     │  │ External     │    │
│  │ control.db   │  │ data.db      │  │ API Gateway  │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## 🏛️ معماری لایه‌ای

### 1. Presentation Layer (لایه نمایش)

**مسئولیت‌ها:**
- رندر کردن صفحات HTML
- مدیریت UI/UX
- تعامل با کاربر

**کامپوننت‌ها:**
- **Templates**: Jinja2 Templates در `app/templates/`
- **Static Files**: CSS, JavaScript, Images در `app/static/`
- **Frontend Libraries**: Bootstrap, Chart.js, Plotly

**ساختار:**
```
app/templates/
├── base.html              # Template پایه
├── index.html             # صفحه اصلی
├── dashboard_list.html     # لیست داشبوردها
├── dashboards/            # Templates داشبوردها
├── admin/                 # Templates پنل ادمین
└── kanban/                # Templates Kanban
```

### 2. Application Layer (لایه اپلیکیشن)

**مسئولیت‌ها:**
- مدیریت Route‌ها
- Business Logic
- کنترل دسترسی
- مدیریت Session

**کامپوننت‌ها:**

#### 2.1. Blueprints

```
app/
├── app.py                 # Main Application
├── dashboard_routes.py    # Dashboard Routes
├── admin/                 # Admin Panel Blueprint
│   └── routes.py
├── kanban.py             # Kanban Blueprint
└── students_dashboard.py # Students Dashboard Blueprint
```

#### 2.2. Authentication & Authorization

**کلاس‌ها و توابع:**
- `auth_utils.py`: Decorator `@requires_auth`
- `app.py`: Routes `/login`, `/authorized`, `/logout`
- `UserContext`: مدیریت Context کاربر
- `AccessLevel`: Enum سطوح دسترسی

**جریان احراز هویت:**
```
User → /login → SSO Server → /authorized → Session Created → Access Granted
```

### 3. Business Logic Layer (لایه منطق کسب‌وکار)

#### 3.1. Dashboard System

**معماری:**
```
dashboards/
├── base.py              # BaseDashboard (Abstract Class)
├── registry.py          # DashboardRegistry (Singleton)
├── context.py           # UserContext Management
├── cache.py             # Caching System
├── config.py            # Configuration
├── utils.py             # Utility Functions
├── data_providers/      # Data Access Layer
│   ├── base.py
│   ├── faculty.py
│   ├── students.py
│   └── lms.py
├── visualizations/      # Reusable Components
│   └── maps.py
└── dashboards/          # Individual Dashboards
    ├── faculty_stats.py
    ├── faculty_map.py
    └── ...
```

**Design Patterns:**
- **Registry Pattern**: برای مدیریت داشبوردها
- **Template Method Pattern**: در BaseDashboard
- **Strategy Pattern**: در Data Providers
- **Factory Pattern**: برای ایجاد داشبوردها

**جریان درخواست داشبورد:**
```
Request → Route Handler → DashboardRegistry.get() 
→ Dashboard.handle_request() → UserContext.get() 
→ Dashboard.check_access() → Dashboard.get_data() 
→ Cache Check → Data Provider → Render Template
```

#### 3.2. Admin Panel

**ساختار:**
```
admin/
├── __init__.py          # Blueprint Definition
├── routes.py            # Admin Routes
├── utils.py             # Admin Utilities
├── scheduler.py         # Auto-sync Scheduler
├── sync_handlers.py     # Sync Handlers
└── sync_progress.py     # Sync Progress Tracking
```

**قابلیت‌ها:**
- مدیریت کاربران
- مدیریت دسترسی داشبوردها
- مدیریت همگام‌سازی داده‌ها
- مشاهده لاگ‌ها

#### 3.3. Data Synchronization

**معماری:**
```
sync_handlers.py
├── run_sync_by_source()     # Main Sync Function
├── run_lms_sync()           # LMS Specific Sync
├── stop_sync_by_source()    # Stop Sync
└── _lms_continuous_sync()   # Continuous LMS Sync

scheduler.py
├── start_scheduler()         # Start Auto-sync
├── stop_scheduler()          # Stop Auto-sync
└── _scheduled_sync()         # Scheduled Task
```

**انواع همگام‌سازی:**
1. **Manual Sync**: همگام‌سازی دستی توسط ادمین
2. **Scheduled Sync**: همگام‌سازی خودکار در بازه‌های زمانی
3. **Continuous Sync**: همگام‌سازی مداوم (فقط برای LMS)

### 4. Data Access Layer (لایه دسترسی به داده)

#### 4.1. ORM Models

**مدل‌های اصلی:**
- `User`: کاربران
- `Project`: پروژه‌ها
- `Task`: تسک‌ها
- `KanbanColumn`: ستون‌های Kanban
- `DashboardAccess`: دسترسی به داشبوردها
- `DataSync`: تنظیمات همگام‌سازی
- `AccessLog`: لاگ دسترسی‌ها

#### 4.2. Data Providers

**BaseDataProvider:**
- `execute_query()`: اجرای Query با فیلتر Context
- `execute_query_dict()`: Query با خروجی Dictionary
- `_apply_context_filters()`: اعمال فیلترهای Context

**Data Providers:**
- `FacultyDataProvider`: داده‌های دانشکده
- `StudentsDataProvider`: داده‌های دانشجویان
- `LMSDataProvider`: داده‌های LMS

#### 4.3. Cache System

**DashboardCache:**
- `get(key)`: دریافت از Cache
- `set(key, value, ttl)`: ذخیره در Cache
- `generate_key()`: تولید کلید Cache

**استراتژی Cache:**
- Cache Key شامل: dashboard_id, access_level, filters
- TTL پیش‌فرض: 300 ثانیه (5 دقیقه)
- Cache در Memory (قابل تغییر به Redis)

---

## 🔄 جریان‌های اصلی سیستم

### 1. جریان ورود کاربر

```
1. User → /login
2. Redirect to SSO Server
3. User Authenticates on SSO
4. SSO → /authorized (with code)
5. Exchange code for token
6. Get user info from SSO
7. Create/Update User in DB
8. Create Session
9. Determine Access Level
10. Redirect to Dashboard
```

### 2. جریان نمایش داشبورد

```
1. User → /dashboards/<dashboard_id>
2. Route Handler → DashboardRegistry.get()
3. Get UserContext
4. Check Access Permission
5. Extract Filters from Request
6. Apply User Context Filters
7. Generate Cache Key
8. Check Cache
9. If Cache Miss:
   - Call Dashboard.get_data()
   - Apply Data Provider Filters
   - Fetch from Database
   - Cache Result
10. Render Template with Data
```

### 3. جریان همگام‌سازی داده

```
1. Scheduler Trigger / Manual Trigger
2. Get DataSync Configuration
3. Check API Credentials
4. For Faculty/Students:
   - Login to API Gateway
   - Get Token
   - Call Data Endpoint
   - Process Response
   - Save to Database
5. For LMS:
   - Call LMS Endpoint
   - Process Response
   - Save to Database
6. Update Sync Status
7. Log Action
```

---

## 🔐 معماری امنیت

### 1. Authentication

**SSO Integration:**
- OAuth2 Flow
- State Parameter برای CSRF Protection
- Token Storage در Session
- Secure Cookie Settings

**Session Management:**
- Flask-Session با File System Storage
- Secure Cookie Flags
- HttpOnly, SameSite Protection

### 2. Authorization

**Role-Based Access Control (RBAC):**
- AccessLevel Enum
- UserContext برای Context-Aware Authorization
- Dashboard Access Control
- Data Filtering بر اساس Context

**Access Control Layers:**
1. Route Level: `@requires_auth`, `@admin_required`
2. Dashboard Level: `check_access()`
3. Data Level: Context Filters در Data Providers

### 3. Data Security

**SQL Injection Prevention:**
- استفاده از Parameterized Queries
- SQLAlchemy ORM

**XSS Prevention:**
- Jinja2 Auto-escaping
- Input Validation

---

## 📊 معماری داده

### 1. Database Schema

**access_control.db:**
- Tables: users, projects, tasks, dashboard_access, data_syncs, access_logs
- Relationships: Foreign Keys, Many-to-Many

**faculty_data.db:**
- Tables: faculty, students, lms_data, monitor_data
- Indexes برای Performance

### 2. Data Flow

```
External API → Data Sync → faculty_data.db → Data Provider → Dashboard → Cache → User
```

### 3. Caching Strategy

**Cache Levels:**
1. Dashboard Level: Cache کل داده‌های داشبورد
2. Query Level: Cache نتایج Query (آینده)

**Cache Invalidation:**
- TTL-based
- Manual Invalidation (آینده)

---

## 🔧 معماری توسعه‌پذیری

### 1. Modularity

**Separation of Concerns:**
- هر ماژول مسئولیت مشخص دارد
- کمترین وابستگی بین ماژول‌ها
- Interface-based Design

### 2. Extensibility

**Adding New Dashboard:**
1. Create Dashboard Class (inherit from BaseDashboard)
2. Register with DashboardRegistry
3. Create Template
4. (Optional) Create Data Provider

**Adding New Data Source:**
1. Create Data Provider (inherit from BaseDataProvider)
2. Add Sync Handler
3. Add to DataSync Configuration

### 3. Configuration Management

**Environment Variables:**
- `.env` file برای تنظیمات حساس
- Config Classes برای تنظیمات عمومی

**Database Configuration:**
- DashboardConfig Table
- DataSync Table

---

## 📈 Performance Considerations

### 1. Caching

- Dashboard Cache با TTL
- Query Result Caching (آینده)

### 2. Database Optimization

- Indexes روی Foreign Keys
- Query Optimization
- Connection Pooling (آینده)

### 3. Frontend Optimization

- Static File Caching
- Minified CSS/JS
- Lazy Loading (آینده)

---

## 🧪 Testing Architecture

### 1. Unit Tests

- Test Data Providers
- Test Dashboard Logic
- Test Utilities

### 2. Integration Tests

- Test Authentication Flow
- Test Dashboard Rendering
- Test Data Sync

### 3. Test Data

- Mock SSO برای Testing
- Test Database
- Fixtures

---

## 📚 Design Patterns استفاده شده

1. **Registry Pattern**: DashboardRegistry
2. **Template Method**: BaseDashboard
3. **Strategy Pattern**: Data Providers
4. **Factory Pattern**: Dashboard Creation
5. **Singleton Pattern**: DashboardRegistry
6. **Decorator Pattern**: `@requires_auth`, `@admin_required`
7. **Observer Pattern**: Event Listeners (SQLAlchemy)

---

**تاریخ آخرین به‌روزرسانی**: 1404/01/15
**نگهدارنده**: تیم توسعه



