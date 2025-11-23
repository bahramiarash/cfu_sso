# راهنمای به‌روزرسانی تمپلیت‌های داشبورد

## خلاصه تغییرات

یک تمپلیت پایه یکپارچه (`dashboard_base.html`) ایجاد شده است که شامل:
- Navigation bar با منوی داشبردها
- اطلاعات کاربر و دکمه خروج
- طراحی Responsive
- Footer

## داشبردهای به‌روزرسانی شده

✅ `d1.html` - آمار اعضای هیئت علمی
✅ `students_dashboard.html` - داشبورد دانشجو معلمان
✅ `dashboard_list.html` - لیست داشبوردها

## داشبردهای نیازمند به‌روزرسانی

⚠️ `d2.html` - نیاز به به‌روزرسانی
⚠️ `d3.html` - نیاز به به‌روزرسانی  
⚠️ `d7.html` - نیاز به به‌روزرسانی
⚠️ `d8.html` - نیاز به به‌روزرسانی

## نحوه به‌روزرسانی

برای هر داشبورد، مراحل زیر را انجام دهید:

### 1. حذف HTML کامل و Head

```html
<!-- حذف این بخش -->
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    ...
</head>
<body>
```

### 2. استفاده از dashboard_base

```html
{% extends "dashboard_base.html" %}

{% block title %}{{ dashboard_title|default('عنوان داشبورد') }}{% endblock %}

{% block content %}
<div class="container">
    <!-- محتوای داشبورد -->
</div>
{% endblock %}
```

### 3. حذف Navigation و Footer

- حذف دکمه‌های خروج و بازگشت
- حذف `<script>` و `<link>` های تکراری (در dashboard_base موجود است)
- حذف `</body></html>` در انتها

### 4. اضافه کردن فیلترها (در صورت نیاز)

```html
{% if show_province_filter or show_faculty_filter %}
{% include 'dashboards/_filters.html' %}
{% endif %}
```

## مثال کامل

### قبل:
```html
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>داشبرد</title>
    <link href="...bootstrap...">
</head>
<body>
{% extends 'base.html' %}
{% block content %}
<div class="container">
    <h1>عنوان</h1>
    <!-- محتوا -->
</div>
{% endblock %}
</body>
</html>
```

### بعد:
```html
{% extends "dashboard_base.html" %}

{% block title %}{{ dashboard_title|default('عنوان داشبورد') }}{% endblock %}

{% block content %}
<div class="container">
    {% if show_province_filter or show_faculty_filter %}
    {% include 'dashboards/_filters.html' %}
    {% endif %}
    
    <!-- محتوای داشبورد -->
</div>
{% endblock %}
```

## مزایای تمپلیت جدید

1. **Navigation یکپارچه**: دسترسی سریع به همه داشبردها از طریق منو
2. **اطلاعات کاربر**: نمایش نام و سطح دسترسی کاربر
3. **Responsive Design**: سازگار با موبایل و تبلت
4. **کاهش تکرار کد**: یک بار تعریف، استفاده در همه جا
5. **نگهداری آسان**: تغییرات در یک فایل اعمال می‌شود


