# جزئیات فنی - سامانه BI دانشگاه فرهنگیان

## 1. مقدمه

این سند شامل جزئیات فنی و تکنیکی سامانه BI دانشگاه فرهنگیان است.

## 2. تکنولوژی‌های استفاده شده

### 2.1 Backend

- **Python**: 3.8+
- **Flask**: 3.1.0 - Framework اصلی
- **SQLAlchemy**: 2.0.41 - ORM
- **Flask-Login**: 0.6.3 - مدیریت Session
- **Flask-Session**: 0.8.0 - Session Management
- **Authlib**: 1.5.2 - OAuth 2.0
- **Waitress**: 3.0.2 - WSGI Server
- **Gunicorn**: 23.0.0 - WSGI Server (Production)

### 2.2 Frontend

- **HTML5**: ساختار صفحات
- **CSS3**: استایل‌دهی
- **JavaScript (ES6+)**: منطق سمت کلاینت
- **Bootstrap**: 5.x - Framework CSS
- **Chart.js**: نمودارها
- **Plotly**: 3.0.1 - نمودارهای پیشرفته و نقشه
- **jQuery**: 3.x - DOM Manipulation

### 2.3 Database

- **SQLite**: 3.x - پایگاه داده اصلی
- **SQLAlchemy**: ORM Layer

### 2.4 Libraries

- **jdatetime**: 5.2.0 - تقویم شمسی
- **pandas**: 2.2.3 - پردازش داده‌ها
- **requests**: 2.32.3 - HTTP Requests
- **python-dotenv**: 1.1.0 - مدیریت Environment Variables

## 3. ساختار پروژه

### 3.1 ساختار کلی

```
cert2/
├── app/                      # Application اصلی
│   ├── __init__.py
│   ├── app.py                # Main application file
│   ├── models.py             # Database models
│   ├── admin_models.py       # Admin panel models
│   ├── auth_utils.py         # Authentication utilities
│   ├── extensions.py         # Flask extensions
│   ├── dashboard_routes.py   # Dashboard routes
│   │
│   ├── admin/                # Admin panel
│   │   ├── routes.py
│   │   ├── scheduler.py
│   │   ├── sync_handlers.py
│   │   └── utils.py
│   │
│   ├── dashboards/           # Dashboard system
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── context.py
│   │   ├── cache.py
│   │   ├── api.py
│   │   ├── dashboards/       # Dashboard implementations
│   │   └── data_providers/   # Data providers
│   │
│   ├── fetch_data/           # Data fetching
│   │   ├── faculty_main.py
│   │   ├── students_main.py
│   │   └── lms_sync.py
│   │
│   ├── templates/            # HTML templates
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── dashboards/
│   │   └── admin/
│   │
│   ├── static/               # Static files
│   │   ├── css/
│   │   ├── js/
│   │   └── images/
│   │
│   └── migrations/           # Database migrations
│
├── docs/                     # Documentation
├── tests/                    # Tests
├── requirements.txt          # Dependencies
└── .env                      # Environment variables
```

### 3.2 ماژول‌های اصلی

#### app.py
- Main application file
- Route definitions
- SSO authentication
- Blueprint registration

#### models.py
- User model
- Project model
- Task model
- Kanban models

#### admin_models.py
- DashboardAccess model
- AccessLog model
- DataSync model
- DashboardConfig model

#### dashboards/base.py
- BaseDashboard class
- Template method pattern
- Error handling

#### dashboards/registry.py
- DashboardRegistry class
- Registration system

#### dashboards/context.py
- UserContext class
- Access level management
- Filter application

## 4. الگوهای طراحی

### 4.1 Registry Pattern

```python
class DashboardRegistry:
    _dashboards: Dict[str, BaseDashboard] = {}
    
    @classmethod
    def register(cls, dashboard_class):
        instance = dashboard_class()
        cls._dashboards[instance.dashboard_id] = instance
```

**استفاده**: برای ثبت خودکار داشبوردها

### 4.2 Strategy Pattern

```python
class BaseDashboard:
    def __init__(self):
        self.data_provider = DataProvider()
    
    def get_data(self, context, **kwargs):
        return self.data_provider.get_data(context, **kwargs)
```

**استفاده**: برای Data Providers

### 4.3 Template Method Pattern

```python
class BaseDashboard(ABC):
    def handle_request(self, user_context, **kwargs):
        # Template method
        if not self.check_access(user_context):
            return self.render_error(...)
        
        data = self.get_data(user_context, **kwargs)
        return self.render(data, user_context)
    
    @abstractmethod
    def get_data(self, context, **kwargs):
        pass
    
    @abstractmethod
    def render(self, data, context):
        pass
```

**استفاده**: برای BaseDashboard

### 4.4 Factory Pattern

```python
def get_user_context(user=None) -> UserContext:
    if user is None:
        user = current_user
    return UserContext(user, user_info)
```

**استفاده**: برای ایجاد UserContext

### 4.5 Singleton Pattern

**استفاده**: برای DashboardRegistry و Cache Manager

## 5. معماری داده

### 5.1 Data Flow

```
User Request
    │
    ▼
Flask Route
    │
    ▼
Dashboard Registry
    │
    ▼
BaseDashboard.handle_request()
    │
    ├─► check_access() ──► UserContext
    │
    ├─► get_data() ──► DataProvider
    │                    │
    │                    ├─► Apply Context Filters
    │                    │
    │                    └─► Query Database
    │
    └─► render() ──► Template
                        │
                        └─► Response
```

### 5.2 Cache Strategy

- **Level**: Dashboard Level
- **Key**: شامل Dashboard ID, Context, Filters
- **TTL**: قابل تنظیم برای هر Dashboard
- **Storage**: In-Memory (می‌تواند به Redis مهاجرت کند)

### 5.3 Database Queries

- استفاده از SQLAlchemy ORM
- Query Optimization
- Lazy Loading برای Relationships
- Eager Loading برای Performance

## 6. امنیت

### 6.1 Authentication

- **OAuth 2.0**: برای SSO
- **Session Management**: Flask-Session
- **CSRF Protection**: State parameter در OAuth

### 6.2 Authorization

- **Role-Based Access Control (RBAC)**
- **Context-Based Filtering**
- **Dashboard-Level Access Control**

### 6.3 Security Headers

```python
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
```

### 6.4 Password Storage

- رمز عبور API در Database ذخیره می‌شود (باید رمزنگاری شود)
- پیشنهاد: استفاده از Encryption برای Production

## 7. Performance

### 7.1 Optimization Techniques

- **Caching**: Dashboard-level caching
- **Lazy Loading**: برای Relationships
- **Query Optimization**: استفاده از Indexes
- **Connection Pooling**: برای Database

### 7.2 Bottlenecks

- SQLite محدودیت در Concurrent Writes
- عدم استفاده از Connection Pooling
- Cache Strategy نیاز به بهبود دارد

## 8. Testing

### 8.1 Test Structure

```
tests/
├── __init__.py
├── test_dashboards.py
├── test_integration.py
└── test_user_access.py
```

### 8.2 Test Coverage

- Unit Tests برای Models
- Integration Tests برای Routes
- Access Control Tests

**نکته**: Coverage کامل نیست و نیاز به بهبود دارد.

## 9. Logging

### 9.1 Log Levels

- **INFO**: اطلاعات عمومی
- **WARNING**: هشدارها
- **ERROR**: خطاها
- **DEBUG**: اطلاعات Debug (فقط در Development)

### 9.2 Log Files

- `app/app.log`: Application logs
- System logs: `/var/log/...`

### 9.3 Log Format

```
%(asctime)s [%(levelname)s] %(message)s
```

## 10. Configuration

### 10.1 Environment Variables

- `SECRET_KEY`: Secret key برای Session
- `SSO_CLIENT_ID`: SSO Client ID
- `SSO_CLIENT_SECRET`: SSO Client Secret
- `SSO_REDIRECT_URI`: SSO Redirect URI
- `ADMIN_USERS`: لیست Admin Users (اختیاری)

### 10.2 Configuration Files

- `.env`: Environment variables
- `config.py`: Configuration class (اختیاری)

## 11. Dependencies

### 11.1 Core Dependencies

```
Flask==3.1.0
Flask-SQLAlchemy==3.1.1
Flask-Login==0.6.3
Flask-Session==0.8.0
Authlib==1.5.2
SQLAlchemy==2.0.41
```

### 11.2 Data Processing

```
pandas==2.2.3
jdatetime==5.2.0
```

### 11.3 HTTP

```
requests==2.32.3
```

### 11.4 Server

```
waitress==3.0.2
gunicorn==23.0.0
```

## 12. Code Style

### 12.1 Python Style

- **PEP 8**: Python style guide
- **Type Hints**: استفاده از Type Hints
- **Docstrings**: مستندسازی کد

### 12.2 Naming Conventions

- **Classes**: PascalCase
- **Functions/Methods**: snake_case
- **Constants**: UPPER_SNAKE_CASE
- **Variables**: snake_case

## 13. Error Handling

### 13.1 Exception Handling

```python
try:
    # Code
except ValueError as e:
    # Handle ValueError
except Exception as e:
    logger.error(f"Error: {e}", exc_info=True)
    return render_template("error.html", error=str(e)), 500
```

### 13.2 Custom Exceptions

```python
class DashboardError(Exception):
    """Custom exception for dashboard errors"""
    pass
```

## 14. Migration Strategy

### 14.1 Database Migrations

- استفاده از Migration Scripts
- فایل‌های Migration در `app/migrations/`

### 14.2 Migration Files

- `create_admin_tables.py`
- `add_user_org_fields.py`
- `add_api_credentials_to_sync.py`
- `add_sync_interval_unit.py`
- `fix_duplicate_syncs.py`

## 15. Deployment

### 15.1 Development

- Flask Development Server
- SQLite Database
- Debug Mode

### 15.2 Production

- Gunicorn یا Waitress
- Nginx Reverse Proxy
- SSL/TLS
- Systemd Service

## 16. Monitoring

### 16.1 Application Monitoring

- Log Files
- Error Tracking
- Performance Metrics

### 16.2 System Monitoring

- System Resources
- Database Performance
- Network Traffic

## 17. بهبودهای آینده

### 17.1 Technical Debt

- [ ] بهبود Error Handling
- [ ] اضافه کردن Unit Tests
- [ ] بهبود Cache Strategy
- [ ] مهاجرت به PostgreSQL
- [ ] استفاده از Redis برای Cache

### 17.2 Performance

- [ ] Query Optimization
- [ ] Connection Pooling
- [ ] CDN برای Static Files
- [ ] Compression

### 17.3 Security

- [ ] Encryption برای Passwords
- [ ] Rate Limiting
- [ ] Security Headers
- [ ] Penetration Testing

---

**تاریخ ایجاد**: 1404  
**آخرین به‌روزرسانی**: 1404

