# Knowledge Management Service

سرویس مدیریت دانش - یک میکروسرویس مستقل برای مدیریت و اشتراک‌گذاری دانش سازمانی

## Overview

این سرویس بخشی از معماری میکروسرویس سیستم BI دانشگاه فرهنگیان است و مسئولیت مدیریت دانش سازمانی را بر عهده دارد.

## Features

- مدیریت مقالات و محتوای دانش
- جستجوی پیشرفته
- دسته‌بندی و تگینگ
- نظرات و تعاملات
- Analytics و گزارش‌گیری
- AI-powered features (Phase 3)

## API Endpoints

### Articles
- `GET /api/knowledge/articles` - لیست مقالات
- `POST /api/knowledge/articles` - ایجاد مقاله
- `GET /api/knowledge/articles/:id` - دریافت مقاله
- `PUT /api/knowledge/articles/:id` - به‌روزرسانی مقاله
- `DELETE /api/knowledge/articles/:id` - حذف مقاله

### Search
- `GET /api/knowledge/search` - جستجوی پیشرفته
- `GET /api/knowledge/search/suggestions` - پیشنهادات جستجو

### Categories
- `GET /api/knowledge/categories` - لیست دسته‌بندی‌ها
- `POST /api/knowledge/categories` - ایجاد دسته‌بندی

### AI Features (Phase 3)
- `POST /api/knowledge/ai/generate` - تولید محتوا
- `POST /api/knowledge/ai/summarize` - خلاصه‌سازی
- `GET /api/knowledge/ai/suggestions` - پیشنهادات

### Analytics
- `GET /api/knowledge/analytics/usage` - آمار استفاده
- `GET /api/knowledge/analytics/popular` - محتوای محبوب

## Setup

### Prerequisites
- Python 3.11+
- Docker (optional)

### Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Run the service:
```bash
python app.py
```

The service will run on port 5008.

### Docker

```bash
docker build -t knowledge-management-service .
docker run -p 5008:5008 knowledge-management-service
```

## Database

The service uses SQLite database stored at `shared/databases/knowledge.db`.

### Schema

- `categories` - دسته‌بندی‌ها
- `tags` - تگ‌ها
- `knowledge_articles` - مقالات
- `article_tags` - رابطه مقالات و تگ‌ها
- `comments` - نظرات
- `bookmarks` - نشان‌گذاری‌ها
- `likes` - لایک‌ها
- `communities` - جوامع تمرین
- `lesson_learned` - درس‌آموخته‌ها
- `search_history` - تاریخچه جستجو

## Development

### Running in Development Mode

```bash
export FLASK_ENV=development
python app.py
```

### Testing

```bash
# Test health endpoint
curl http://localhost:5008/health

# Test articles endpoint
curl http://localhost:5008/api/knowledge/articles
```

## Integration

This service integrates with:
- **Auth Service**: For authentication and user management
- **Admin Service**: For access control and reporting
- **Redis**: For caching (optional)

## Documentation

For complete documentation, see:
- [Proposal Document](../Docs/PROPOSAL_KNOWLEDGE_MANAGEMENT_SYSTEM.md)
- [Service Architecture](../Docs/KNOWLEDGE_MANAGEMENT_SERVICE.md)

## License

[Your License Here]

