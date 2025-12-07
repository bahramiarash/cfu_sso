# سند طراحی - سیستم BI دانشگاه

## 📋 فهرست مطالب

1. [معماری طراحی](#معماری-طراحی)
2. [طراحی دیتابیس](#طراحی-دیتابیس)
3. [طراحی API](#طراحی-api)
4. [طراحی رابط کاربری](#طراحی-رابط-کاربری)
5. [الگوهای طراحی](#الگوهای-طراحی)
6. [جریان‌های کاری](#جریان‌های-کاری)

---

## 🏗️ معماری طراحی

### 1. معماری کلی

سیستم بر اساس **معماری سه‌لایه** (Three-Tier Architecture) طراحی شده است:

```
┌─────────────────────────────────────┐
│   Presentation Tier                  │
│   - Templates                        │
│   - Static Files                     │
│   - JavaScript                       │
└─────────────────────────────────────┘
              ↕
┌─────────────────────────────────────┐
│   Application Tier                   │
│   - Routes                           │
│   - Business Logic                   │
│   - Controllers                      │
└─────────────────────────────────────┘
              ↕
┌─────────────────────────────────────┐
│   Data Tier                         │
│   - Models                           │
│   - Data Providers                   │
│   - Database                         │
└─────────────────────────────────────┘
```

### 2. اصول طراحی

#### 2.1. Separation of Concerns
- هر ماژول مسئولیت مشخص دارد
- Business Logic جدا از Data Access
- Presentation جدا از Business Logic

#### 2.2. DRY (Don't Repeat Yourself)
- Utility Functions مشترک
- Base Classes برای Inheritance
- Configuration متمرکز

#### 2.3. SOLID Principles

**Single Responsibility:**
- هر کلاس یک مسئولیت دارد
- مثال: `BaseDashboard` فقط مدیریت داشبورد

**Open/Closed:**
- Open for Extension
- Closed for Modification
- مثال: Dashboard جدید بدون تغییر BaseDashboard

**Liskov Substitution:**
- Subclasses قابل جایگزینی با Base Class
- مثال: هر Dashboard قابل استفاده به جای BaseDashboard

**Interface Segregation:**
- Interfaces کوچک و متمرکز
- مثال: DataProvider Interface

**Dependency Inversion:**
- وابستگی به Abstraction نه Implementation
- مثال: Dashboard وابسته به DataProvider Interface

---

## 🗄️ طراحی دیتابیس

### 1. Entity Relationship Diagram (ERD)

```
┌─────────────┐         ┌──────────────┐
│    User     │─────────│ AccessLevel   │
└─────────────┘         └──────────────┘
      │
      │ 1:N
      │
┌─────────────┐         ┌──────────────┐
│  Project    │─────────│ KanbanColumn │
└─────────────┘         └──────────────┘
      │                        │
      │                        │ 1:N
      │                        │
      │                  ┌─────────────┐
      │                  │    Task     │
      │                  └─────────────┘
      │
      │ N:M
      │
┌─────────────┐
│   Member    │
└─────────────┘

┌─────────────┐         ┌──────────────┐
│    User     │─────────│DashboardAccess│
└─────────────┘         └──────────────┘

┌─────────────┐         ┌──────────────┐
│  DataSync   │─────────│  AccessLog    │
└─────────────┘         └──────────────┘
```

### 2. جداول اصلی

#### 2.1. users
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    sso_id TEXT NOT NULL UNIQUE,
    province_code INTEGER,
    university_code INTEGER,
    faculty_code INTEGER
);
```

**Indexes:**
- `sso_id`: UNIQUE INDEX
- `province_code`: INDEX
- `faculty_code`: INDEX

#### 2.2. projects
```sql
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    title TEXT,
    description TEXT,
    creator_id INTEGER REFERENCES users(id),
    owner_id INTEGER REFERENCES users(id),
    start_date DATETIME,
    end_date DATETIME,
    updated_at DATETIME
);
```

#### 2.3. dashboard_access
```sql
CREATE TABLE dashboard_access (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    dashboard_id TEXT NOT NULL,
    can_access BOOLEAN DEFAULT TRUE,
    filter_restrictions JSON,
    date_from DATETIME,
    date_to DATETIME,
    created_at DATETIME,
    updated_at DATETIME
);
```

#### 2.4. data_syncs
```sql
CREATE TABLE data_syncs (
    id INTEGER PRIMARY KEY,
    data_source TEXT NOT NULL UNIQUE,
    sync_type TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    auto_sync_enabled BOOLEAN DEFAULT TRUE,
    sync_interval_value INTEGER DEFAULT 60,
    sync_interval_unit TEXT DEFAULT 'minutes',
    api_endpoint TEXT,
    api_username TEXT,
    api_password TEXT,
    last_sync_at DATETIME,
    next_sync_at DATETIME,
    records_synced INTEGER DEFAULT 0
);
```

### 3. روابط (Relationships)

#### 3.1. One-to-Many
- User → Projects (creator_id, owner_id)
- Project → Tasks
- Project → KanbanColumns
- User → AccessLogs

#### 3.2. Many-to-Many
- Users ↔ Projects (project_members)
- Users ↔ KanbanColumns (kanban_column_users)
- Users ↔ Tasks (task_assigned_users)

### 4. Constraints

**Foreign Keys:**
- تمام Foreign Keys با `ON DELETE CASCADE` یا `ON DELETE SET NULL`

**Unique Constraints:**
- `users.sso_id`: UNIQUE
- `data_syncs.data_source`: UNIQUE
- `dashboard_access(user_id, dashboard_id)`: UNIQUE

---

## 🔌 طراحی API

### 1. RESTful Endpoints

#### 1.1. Authentication
```
POST   /login              # Initiate SSO login
GET    /authorized         # SSO callback
GET    /logout             # Logout user
```

#### 1.2. Dashboards
```
GET    /dashboards/                    # List dashboards
GET    /dashboards/<dashboard_id>      # Show dashboard
GET    /api/dashboards/<id>/filters    # Get filter options
```

#### 1.3. Admin Panel
```
GET    /admin/                         # Admin dashboard
GET    /admin/users                    # List users
GET    /admin/users/<id>                # User detail
POST   /admin/users/<id>/edit           # Edit user
GET    /admin/dashboard-access          # List accesses
POST   /admin/data-sync/<id>/sync       # Trigger sync
GET    /admin/data-sync/<id>/progress   # Get sync progress
```

### 2. Response Formats

#### 2.1. Success Response
```json
{
    "success": true,
    "data": { ... },
    "message": "Operation successful"
}
```

#### 2.2. Error Response
```json
{
    "success": false,
    "error": "Error message",
    "code": "ERROR_CODE"
}
```

### 3. Authentication

**Headers:**
```
Authorization: Bearer <token>
Content-Type: application/json
```

**Session-based:**
- استفاده از Flask Session
- Cookie-based Authentication

---

## 🎨 طراحی رابط کاربری

### 1. Layout Structure

```
┌─────────────────────────────────────────┐
│           Header (Navigation)            │
├─────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────────────────┐ │
│  │ Sidebar   │  │   Main Content       │ │
│  │ (Menu)    │  │   (Dashboard)        │ │
│  │           │  │                      │ │
│  └──────────┘  └──────────────────────┘ │
├─────────────────────────────────────────┤
│           Footer                         │
└─────────────────────────────────────────┘
```

### 2. Design System

#### 2.1. Colors
- **Primary**: #007bff (Bootstrap Blue)
- **Success**: #28a745 (Green)
- **Warning**: #ffc107 (Yellow)
- **Danger**: #dc3545 (Red)
- **Info**: #17a2b8 (Cyan)

#### 2.2. Typography
- **Font Family**: Tahoma, Arial (برای فارسی)
- **RTL Support**: `dir="rtl"` در HTML
- **Font Size**: 14px base

#### 2.3. Components

**Buttons:**
- Primary, Secondary, Success, Danger
- Sizes: Small, Medium, Large

**Cards:**
- Shadow: `box-shadow: 0 2px 4px rgba(0,0,0,0.1)`
- Border-radius: `4px`

**Tables:**
- Striped rows
- Hover effect
- Responsive

### 3. Responsive Design

**Breakpoints:**
- Mobile: < 768px
- Tablet: 768px - 992px
- Desktop: > 992px

**Strategies:**
- Bootstrap Grid System
- Mobile-first Approach
- Collapsible Sidebar

---

## 🎯 الگوهای طراحی

### 1. Registry Pattern

**DashboardRegistry:**
```python
class DashboardRegistry:
    _dashboards = {}
    
    @classmethod
    def register(cls, dashboard_class):
        instance = dashboard_class()
        cls._dashboards[instance.dashboard_id] = instance
        return dashboard_class
    
    @classmethod
    def get(cls, dashboard_id):
        return cls._dashboards.get(dashboard_id)
```

**استفاده:**
- مدیریت متمرکز داشبوردها
- Auto-registration
- Singleton Pattern

### 2. Template Method Pattern

**BaseDashboard:**
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

**مزایا:**
- تعریف الگوی کلی
- قابلیت Override در Subclasses
- کاهش کدهای تکراری

### 3. Strategy Pattern

**Data Providers:**
```python
class BaseDataProvider(ABC):
    @abstractmethod
    def get_data(self, context, filters):
        pass

class FacultyDataProvider(BaseDataProvider):
    def get_data(self, context, filters):
        # Faculty-specific logic
        pass
```

**مزایا:**
- قابلیت تعویض Algorithm
- جداسازی Logic
- قابلیت تست آسان

### 4. Factory Pattern

**Dashboard Creation:**
```python
@DashboardRegistry.register
class FacultyStatsDashboard(BaseDashboard):
    def __init__(self):
        super().__init__(
            dashboard_id="d1",
            title="آمار دانشکده‌ها"
        )
```

**مزایا:**
- Encapsulation از Creation Logic
- قابلیت Extension
- کاهش Coupling

---

## 🔄 جریان‌های کاری

### 1. جریان ورود کاربر

```
[User] → [Login Page] → [SSO Server]
                              ↓
[SSO Server] → [Authorized Callback] → [Create Session]
                              ↓
[Session Created] → [Determine Access Level] → [Redirect to Dashboard]
```

**State Diagram:**
```
[Not Authenticated] → [SSO Login] → [Authenticated] → [Session Active]
                                                           ↓
                                                    [Session Expired]
                                                           ↓
                                                    [Not Authenticated]
```

### 2. جریان نمایش داشبورد

```
[User Request] → [Route Handler] → [Get Dashboard from Registry]
                                          ↓
[Check Access] → [Get User Context] → [Extract Filters]
                                          ↓
[Generate Cache Key] → [Check Cache] → [Cache Hit?]
                                          ↓ No
[Get Data from Provider] → [Apply Filters] → [Cache Result]
                                          ↓
[Render Template] → [Return Response]
```

### 3. جریان همگام‌سازی داده

```
[Scheduler/Manual Trigger] → [Get Sync Config] → [Check Status]
                                          ↓
[Status = Running?] → [Yes: Return] → [No: Continue]
                                          ↓
[For Faculty/Students:] → [Login to API] → [Get Token]
                                          ↓
[Call Data Endpoint] → [Process Response] → [Save to DB]
                                          ↓
[Update Sync Status] → [Log Action] → [Calculate Next Sync]
```

---

## 🔐 طراحی امنیت

### 1. Authentication Flow

**OAuth2 Flow:**
```
1. User → /login
2. Generate State (CSRF Protection)
3. Redirect to SSO with State
4. User Authenticates
5. SSO Redirects with Code + State
6. Verify State
7. Exchange Code for Token
8. Get User Info
9. Create Session
```

### 2. Authorization Model

**Access Control Matrix:**
```
                | Central | Province | Faculty | Admin
----------------|---------|----------|---------|-------
All Data        |   ✓     |    ✗     |    ✗    |   ✓
Province Data   |   ✓     |    ✓     |    ✗    |   ✓
Faculty Data    |   ✓     |    ✓     |    ✓    |   ✓
Admin Panel     |   ✗     |    ✗     |    ✗    |   ✓
```

### 3. Data Filtering

**Context-Based Filtering:**
```python
if access_level == CENTRAL_ORG:
    # No filters - can see all
    filters = {}
elif access_level == PROVINCE_UNIVERSITY:
    # Filter by province
    filters = {'province_code': user.province_code}
elif access_level == FACULTY:
    # Filter by faculty
    filters = {'faculty_code': user.faculty_code}
```

---

## 📊 طراحی Performance

### 1. Caching Strategy

**Cache Levels:**
1. **Dashboard Level**: Cache کل داده‌های داشبورد
2. **Query Level**: Cache نتایج Query (آینده)

**Cache Key Structure:**
```
dashboard:{dashboard_id}:{access_level}:{province_code}:{faculty_code}:{filters_hash}
```

**TTL Strategy:**
- Default: 300 seconds (5 minutes)
- Configurable per Dashboard
- Manual Invalidation (آینده)

### 2. Database Optimization

**Indexes:**
- Foreign Keys
- Frequently Queried Columns
- Composite Indexes برای Queries پیچیده

**Query Optimization:**
- استفاده از JOIN به جای Multiple Queries
- LIMIT برای Pagination
- SELECT فقط Columns مورد نیاز

### 3. Frontend Optimization

**Static Files:**
- Minified CSS/JS
- Browser Caching
- CDN (آینده)

**Lazy Loading:**
- Charts: Load on Demand
- Images: Lazy Load

---

## 🧪 طراحی تست

### 1. Unit Tests

**Coverage:**
- Data Providers
- Dashboard Logic
- Utility Functions
- Models

**Mock Objects:**
- Mock Database
- Mock SSO
- Mock API Responses

### 2. Integration Tests

**Scenarios:**
- Authentication Flow
- Dashboard Rendering
- Data Sync
- Admin Operations

### 3. Test Data

**Fixtures:**
- Test Users
- Test Projects
- Test Data

---

**تاریخ آخرین به‌روزرسانی**: 1404/01/15
**نگهدارنده**: تیم توسعه



