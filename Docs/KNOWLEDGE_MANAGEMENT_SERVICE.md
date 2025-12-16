# مستندات فنی سرویس مدیریت دانش

**نسخه**: 1.0  
**تاریخ آخرین به‌روزرسانی**: ۱۶ دسامبر ۲۰۲۵  
**وضعیت**: در حال توسعه - فاز 1

---

## معماری سرویس

### نمای کلی

سرویس مدیریت دانش به عنوان یک میکروسرویس مستقل در معماری میکروسرویس سیستم BI پیاده‌سازی شده است.

```
┌─────────────────────────────────────────┐
│         API Gateway (Nginx)             │
│         /knowledge/*                     │
│         /api/knowledge/*                 │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│   Knowledge Management Service          │
│   Port: 5008                            │
│   - Flask Application                   │
│   - REST API                            │
│   - Authentication (JWT)                │
└─────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
┌──────────┐  ┌──────────┐  ┌──────────┐
│Database  │  │  Auth    │  │  Redis   │
│SQLite    │  │ Service  │  │ (Future)│
│knowledge │  │          │  │          │
│.db       │  │          │  │          │
└──────────┘  └──────────┘  └──────────┘
```

### Stack فناوری

- **Backend**: Flask 3.1.0 (Python 3.11)
- **Database**: SQLite (برای شروع) / PostgreSQL (برای production)
- **ORM**: SQLAlchemy
- **Authentication**: JWT tokens از Auth Service
- **API**: RESTful

---

## ساختار دایرکتوری

```
services/knowledge-management-service/
├── __init__.py
├── app.py                    # Main Flask application
├── models.py                 # Database models
├── extensions.py             # Flask extensions
├── utils.py                  # Utility functions
├── requirements.txt          # Python dependencies
├── Dockerfile               # Docker configuration
├── README.md                # Service documentation
└── api/
    ├── __init__.py
    ├── articles.py          # Article endpoints
    ├── categories.py        # Category endpoints
    ├── search.py            # Search endpoints
    ├── ai.py                # AI-powered features
    └── analytics.py         # Analytics endpoints
```

---

## Database Schema

### جداول اصلی

#### 1. categories
- `id` (Integer, Primary Key)
- `name` (String, Unique)
- `description` (Text)
- `parent_id` (Integer, Foreign Key to categories.id)
- `icon` (String)
- `created_at` (DateTime)

#### 2. tags
- `id` (Integer, Primary Key)
- `name` (String, Unique)
- `usage_count` (Integer)
- `created_at` (DateTime)

#### 3. knowledge_articles
- `id` (Integer, Primary Key)
- `title` (String)
- `content` (Text)
- `summary` (Text)
- `author_id` (Integer) - References users.id in auth service
- `category_id` (Integer, Foreign Key to categories.id)
- `status` (String) - draft, published, archived
- `views_count` (Integer)
- `likes_count` (Integer)
- `comments_count` (Integer)
- `created_at` (DateTime)
- `updated_at` (DateTime)

#### 4. article_tags (Many-to-Many)
- `article_id` (Integer, Foreign Key, Primary Key)
- `tag_id` (Integer, Foreign Key, Primary Key)
- `created_at` (DateTime)

#### 5. comments
- `id` (Integer, Primary Key)
- `article_id` (Integer, Foreign Key)
- `user_id` (Integer) - References users.id
- `content` (Text)
- `parent_id` (Integer, Foreign Key to comments.id) - For nested comments
- `created_at` (DateTime)
- `updated_at` (DateTime)

#### 6. bookmarks
- `id` (Integer, Primary Key)
- `article_id` (Integer, Foreign Key)
- `user_id` (Integer)
- `created_at` (DateTime)

#### 7. likes
- `id` (Integer, Primary Key)
- `article_id` (Integer, Foreign Key)
- `user_id` (Integer)
- `created_at` (DateTime)

#### 8. communities
- `id` (Integer, Primary Key)
- `name` (String, Unique)
- `description` (Text)
- `creator_id` (Integer)
- `member_count` (Integer)
- `is_active` (Boolean)
- `created_at` (DateTime)

#### 9. lesson_learned
- `id` (Integer, Primary Key)
- `title` (String)
- `content` (Text)
- `project_id` (Integer)
- `author_id` (Integer)
- `tags` (JSON) - Array of tag names
- `created_at` (DateTime)
- `updated_at` (DateTime)

#### 10. search_history
- `id` (Integer, Primary Key)
- `user_id` (Integer, Nullable)
- `query` (String)
- `results_count` (Integer)
- `created_at` (DateTime)

---

## API Documentation

### Base URL
- Development: `http://localhost:5008`
- Production: `https://bi.cfu.ac.ir/api/knowledge`

### Authentication

تمام endpointهای نیازمند authentication از JWT token استفاده می‌کنند:

```
Authorization: Bearer <token>
```

یا از طریق cookie:
```
Cookie: auth_token=<token>
```

---

### Articles API

#### GET /api/knowledge/articles
لیست مقالات

**Query Parameters:**
- `page` (int, default: 1) - شماره صفحه
- `per_page` (int, default: 20) - تعداد در هر صفحه
- `category_id` (int, optional) - فیلتر بر اساس دسته‌بندی
- `status` (string, default: 'published') - وضعیت مقاله
- `search` (string, optional) - جستجو در عنوان و محتوا

**Response:**
```json
{
  "articles": [...],
  "total": 100,
  "page": 1,
  "per_page": 20,
  "pages": 5
}
```

#### POST /api/knowledge/articles
ایجاد مقاله جدید

**Request Body:**
```json
{
  "title": "عنوان مقاله",
  "content": "محتوای مقاله",
  "summary": "خلاصه مقاله",
  "category_id": 1,
  "status": "draft",
  "tags": ["tag1", "tag2"]
}
```

**Response:** 201 Created

#### GET /api/knowledge/articles/:id
دریافت مقاله

**Response:**
```json
{
  "id": 1,
  "title": "...",
  "content": "...",
  "author_id": 123,
  "views_count": 50,
  ...
}
```

#### PUT /api/knowledge/articles/:id
به‌روزرسانی مقاله

**Request Body:** (همانند POST، فیلدهای اختیاری)

**Response:** 200 OK

#### DELETE /api/knowledge/articles/:id
حذف مقاله

**Response:** 200 OK

---

### Search API

#### GET /api/knowledge/search
جستجوی پیشرفته

**Query Parameters:**
- `q` (string, required) - عبارت جستجو
- `category_id` (int, optional)
- `tag` (string, optional)
- `page` (int, default: 1)
- `per_page` (int, default: 20)

**Response:**
```json
{
  "articles": [...],
  "total": 25,
  "page": 1,
  "query": "search term"
}
```

#### GET /api/knowledge/search/suggestions
پیشنهادات جستجو

**Query Parameters:**
- `q` (string, required) - حداقل 2 کاراکتر

**Response:**
```json
{
  "suggestions": ["suggestion1", "suggestion2", ...]
}
```

---

### Categories API

#### GET /api/knowledge/categories
لیست دسته‌بندی‌ها

**Response:**
```json
{
  "categories": [
    {
      "id": 1,
      "name": "دسته‌بندی",
      "parent_id": null,
      ...
    }
  ]
}
```

#### POST /api/knowledge/categories
ایجاد دسته‌بندی جدید

**Request Body:**
```json
{
  "name": "نام دسته‌بندی",
  "description": "توضیحات",
  "parent_id": null,
  "icon": "icon-name"
}
```

---

### AI API (Phase 3)

#### POST /api/knowledge/ai/generate
تولید محتوا با AI

**Request Body:**
```json
{
  "prompt": "درخواست",
  "type": "article"
}
```

#### POST /api/knowledge/ai/summarize
خلاصه‌سازی محتوا

**Request Body:**
```json
{
  "content": "متن برای خلاصه‌سازی"
}
```

#### GET /api/knowledge/ai/suggestions
پیشنهادات هوشمند

---

### Analytics API

#### GET /api/knowledge/analytics/usage
آمار استفاده

**Response:**
```json
{
  "total_articles": 150,
  "published_articles": 120,
  "total_views": 5000,
  "total_searches": 300,
  "most_viewed": [...]
}
```

#### GET /api/knowledge/analytics/popular
محتوای محبوب

**Response:**
```json
{
  "most_liked": [...],
  "most_commented": [...],
  "popular_tags": [...]
}
```

---

## Integration Guide

### با Auth Service

سرویس مدیریت دانش از Auth Service برای authentication استفاده می‌کند:

```python
from utils.auth_client import AuthClient

AUTH_SERVICE_URL = "http://auth-service:5001"
auth_client = AuthClient(AUTH_SERVICE_URL)

# Validate token
result = auth_client.validate_token(token)
```

### با Admin Service

برای مدیریت دسترسی‌ها و گزارش‌گیری می‌توان از Admin Service استفاده کرد.

### با Redis (آینده)

برای caching و بهبود عملکرد:

```python
import redis

redis_client = redis.Redis(host='redis', port=6379)
```

---

## Deployment

### Docker

```bash
# Build
docker build -t knowledge-management-service ./services/knowledge-management-service

# Run
docker run -p 5006:5006 knowledge-management-service
```

### Docker Compose

سرویس به صورت خودکار در `docker-compose.yml` تعریف شده است:

```bash
docker-compose up knowledge-management-service
```

### Environment Variables

```env
SECRET_KEY=your-secret-key
AUTH_SERVICE_URL=http://auth-service:5001
DATABASE_URL=sqlite:///databases/knowledge.db
```

---

## Development

### Setup

```bash
cd services/knowledge-management-service
pip install -r requirements.txt
python app.py
```

### Testing

```bash
# Health check
curl http://localhost:5008/health

# List articles
curl http://localhost:5008/api/knowledge/articles
```

---

## Roadmap

### فاز 1: Foundation (ماه 1-2) ✅
- [x] ساختار اولیه سرویس
- [x] Database schema
- [x] CRUD operations برای مقالات
- [x] جستجوی پایه

### فاز 2: Core Features (ماه 3-4)
- [ ] جستجوی پیشرفته
- [ ] سیستم نظرات
- [ ] Bookmarks و Likes
- [ ] Analytics پیشرفته

### فاز 3: AI Features (ماه 5-6)
- [ ] Integration با AI
- [ ] تولید محتوا
- [ ] خلاصه‌سازی
- [ ] پیشنهادات هوشمند

### فاز 4: Advanced Features (ماه 7-8)
- [ ] جوامع تمرین
- [ ] درس‌آموخته‌ها
- [ ] Mobile app
- [ ] یکپارچگی با سیستم‌های خارجی

---

## Troubleshooting

### مشکل: Port 5008 در حال استفاده است

```bash
# Windows
netstat -ano | findstr :5008
taskkill /F /PID <PID>

# Linux
lsof -i :5008
kill -9 <PID>
```

### مشکل: Database ایجاد نمی‌شود

بررسی کنید که دایرکتوری `shared/databases` وجود دارد و قابل نوشتن است.

### مشکل: Authentication failed

بررسی کنید که:
1. Auth Service در حال اجرا است
2. AUTH_SERVICE_URL صحیح است
3. JWT token معتبر است

---

## Support

برای پشتیبانی و سوالات:
- مستندات کامل: [Proposal Document](PROPOSAL_KNOWLEDGE_MANAGEMENT_SYSTEM.md)
- Issues: [GitHub Issues] (اگر استفاده می‌کنید)

---

**آخرین به‌روزرسانی**: ۱۶ دسامبر ۲۰۲۵

