# مستندات کامل UI/UX سیستم BI دانشگاه

## 📋 فهرست مطالب

1. [اصول طراحی UI/UX](#اصول-طراحی-uiux)
2. [ساختار Layout](#ساختار-layout)
3. [کامپوننت‌های UI](#کامپوننت‌های-ui)
4. [صفحات اصلی](#صفحات-اصلی)
5. [Responsive Design](#responsive-design)
6. [دسترسی‌پذیری (Accessibility)](#دسترسی‌پذیری-accessibility)
7. [راهنمای Style Guide](#راهنمای-style-guide)

---

## اصول طراحی UI/UX

### اصول کلی

1. **RTL Support**: تمام صفحات از راست به چپ
2. **فارسی**: استفاده از فونت فارسی (Vazir)
3. **تقویم شمسی**: نمایش تاریخ به صورت شمسی
4. **سادگی**: رابط کاربری ساده و واضح
5. **سازگاری**: سازگاری با مرورگرهای مختلف

### رنگ‌بندی

```css
/* رنگ‌های اصلی */
--primary-color: #007bff;
--secondary-color: #6c757d;
--success-color: #28a745;
--danger-color: #dc3545;
--warning-color: #ffc107;
--info-color: #17a2b8;

/* رنگ‌های پس‌زمینه */
--bg-light: #f8f9fa;
--bg-white: #ffffff;
--bg-dark: #343a40;

/* رنگ‌های متن */
--text-primary: #212529;
--text-secondary: #6c757d;
--text-muted: #6c757d;
```

---

## ساختار Layout

### Base Template

```html
<!-- app/templates/base.html -->
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}سیستم BI دانشگاه{% endblock %}</title>
    
    <!-- Bootstrap RTL -->
    <link href="{{ url_for('static', filename='bootstrap.rtl.min.css') }}" rel="stylesheet">
    
    <!-- Custom CSS -->
    <link href="{{ url_for('static', filename='style.css') }}" rel="stylesheet">
    
    <!-- Fonts -->
    <link href="{{ url_for('static', filename='fonts/Vazir.css') }}" rel="stylesheet">
</head>
<body>
    <!-- Navigation -->
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
        <div class="container-fluid">
            <a class="navbar-brand" href="{{ url_for('index') }}">سیستم BI</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('dashboard.dashboard_list') }}">داشبوردها</a>
                    </li>
                    {% if current_user.is_authenticated and current_user.is_admin() %}
                    <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('admin.index') }}">پنل مدیریت</a>
                    </li>
                    {% endif %}
                </ul>
                <ul class="navbar-nav">
                    {% if current_user.is_authenticated %}
                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" id="userDropdown" role="button" data-bs-toggle="dropdown">
                            {{ current_user.name }}
                        </a>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-item" href="{{ url_for('logout') }}">خروج</a></li>
                        </ul>
                    </li>
                    {% else %}
                    <li class="nav-item">
                        <a class="nav-link" href="{{ url_for('login') }}">ورود</a>
                    </li>
                    {% endif %}
                </ul>
            </div>
        </div>
    </nav>
    
    <!-- Main Content -->
    <main class="container-fluid mt-4">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        {% block content %}{% endblock %}
    </main>
    
    <!-- Footer -->
    <footer class="mt-5 py-3 bg-light text-center">
        <p class="text-muted">© 1404 سیستم BI دانشگاه</p>
    </footer>
    
    <!-- Scripts -->
    <script src="{{ url_for('static', filename='jquery.min.js') }}"></script>
    <script src="{{ url_for('static', filename='bootstrap.bundle.min.js') }}"></script>
    {% block scripts %}{% endblock %}
</body>
</html>
```

### Dashboard Base Template

```html
<!-- app/templates/dashboard_base.html -->
{% extends "base.html" %}

{% block content %}
<div class="row">
    <!-- Sidebar -->
    <div class="col-md-3">
        <div class="card">
            <div class="card-header">
                <h5>فیلترها</h5>
            </div>
            <div class="card-body">
                {% include 'dashboards/_filters.html' %}
            </div>
        </div>
    </div>
    
    <!-- Main Dashboard -->
    <div class="col-md-9">
        <div class="card">
            <div class="card-header">
                <h4>{{ dashboard_title }}</h4>
                {% if dashboard_description %}
                <p class="text-muted">{{ dashboard_description }}</p>
                {% endif %}
            </div>
            <div class="card-body">
                {% block dashboard_content %}{% endblock %}
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

---

## کامپوننت‌های UI

### 1. فیلترها

```html
<!-- app/templates/dashboards/_filters.html -->
<form id="dashboardFilters" method="GET">
    {% if user_context.can_filter_by_province %}
    <div class="mb-3">
        <label for="province_code" class="form-label">استان</label>
        <select class="form-select" id="province_code" name="province_code">
            <option value="">همه استان‌ها</option>
            <!-- Options populated via JavaScript -->
        </select>
    </div>
    {% endif %}
    
    {% if user_context.can_filter_by_faculty %}
    <div class="mb-3">
        <label for="faculty_code" class="form-label">دانشکده</label>
        <select class="form-select" id="faculty_code" name="faculty_code">
            <option value="">همه دانشکده‌ها</option>
        </select>
    </div>
    {% endif %}
    
    <div class="mb-3">
        <label for="date_from" class="form-label">از تاریخ</label>
        <input type="text" class="form-control" id="date_from" name="date_from" placeholder="1403/01/01">
    </div>
    
    <div class="mb-3">
        <label for="date_to" class="form-label">تا تاریخ</label>
        <input type="text" class="form-control" id="date_to" name="date_to" placeholder="1403/12/29">
    </div>
    
    <button type="submit" class="btn btn-primary w-100">اعمال فیلتر</button>
    <button type="button" class="btn btn-secondary w-100 mt-2" onclick="resetFilters()">پاک کردن</button>
</form>

<script>
// Initialize date pickers (Jalali)
$('#date_from, #date_to').kamaDatepicker({
    buttonsColor: "blue",
    markToday: true,
    markHolidays: true,
    gotoToday: true
});
</script>
```

### 2. نمودارها

```html
<!-- استفاده از Chart.js -->
<canvas id="myChart"></canvas>

<script>
const ctx = document.getElementById('myChart').getContext('2d');
const chart = new Chart(ctx, {
    type: 'line',
    data: {
        labels: {{ chart_labels | tojson }},
        datasets: [{
            label: 'داده‌ها',
            data: {{ chart_data | tojson }},
            borderColor: 'rgb(75, 192, 192)',
            tension: 0.1
        }]
    },
    options: {
        responsive: true,
        plugins: {
            legend: {
                position: 'top',
            },
            title: {
                display: true,
                text: 'عنوان نمودار'
            }
        },
        scales: {
            y: {
                beginAtZero: true
            }
        }
    }
});
</script>
```

### 3. جداول

```html
<div class="table-responsive">
    <table class="table table-striped table-hover">
        <thead>
            <tr>
                <th>ردیف</th>
                <th>استان</th>
                <th>تعداد</th>
                <th>درصد</th>
            </tr>
        </thead>
        <tbody>
            {% for row in table_data %}
            <tr>
                <td>{{ row.rownum }}</td>
                <td>{{ row.province_name }}</td>
                <td>{{ row.count | number_format }}</td>
                <td>{{ row.percentage }}%</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
```

### 4. نقشه‌ها

```html
<!-- نقشه با GeoPandas و Matplotlib -->
<img src="{{ url_for('dashboard.map_image', dashboard_id='d2') }}" alt="نقشه" class="img-fluid">
```

---

## صفحات اصلی

### 1. صفحه اصلی (Index)

```html
<!-- app/templates/index.html -->
{% extends "base.html" %}

{% block content %}
<div class="row">
    <div class="col-md-12">
        <div class="jumbotron">
            <h1 class="display-4">خوش آمدید</h1>
            <p class="lead">سیستم هوش تجاری دانشگاه</p>
            <hr class="my-4">
            <p>برای مشاهده داشبوردها، از منوی بالا استفاده کنید.</p>
            <a class="btn btn-primary btn-lg" href="{{ url_for('dashboard.dashboard_list') }}" role="button">
                مشاهده داشبوردها
            </a>
        </div>
    </div>
</div>

<div class="row mt-4">
    <div class="col-md-4">
        <div class="card">
            <div class="card-body">
                <h5 class="card-title">داشبوردها</h5>
                <p class="card-text">مشاهده و تحلیل داده‌های دانشگاهی</p>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card">
            <div class="card-body">
                <h5 class="card-title">گزارش‌ها</h5>
                <p class="card-text">گزارش‌های تحلیلی و آماری</p>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card">
            <div class="card-body">
                <h5 class="card-title">پروژه‌ها</h5>
                <p class="card-text">مدیریت پروژه‌ها و وظایف</p>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

### 2. لیست داشبوردها

```html
<!-- app/templates/dashboard_list.html -->
{% extends "base.html" %}

{% block content %}
<div class="row">
    <div class="col-md-12">
        <h2>داشبوردها</h2>
        <div class="row">
            {% for dashboard in accessible_dashboards %}
            <div class="col-md-4 mb-4">
                <div class="card h-100">
                    <div class="card-body">
                        <h5 class="card-title">{{ dashboard.dashboard_title }}</h5>
                        {% if dashboard.dashboard_description %}
                        <p class="card-text">{{ dashboard.dashboard_description }}</p>
                        {% endif %}
                        <a href="{{ url_for('dashboard.show_dashboard', dashboard_id=dashboard.dashboard_id) }}" 
                           class="btn btn-primary">
                            مشاهده داشبورد
                        </a>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
</div>
{% endblock %}
```

### 3. داشبورد نمونه (D1)

```html
<!-- app/templates/dashboards/d1.html -->
{% extends "dashboard_base.html" %}

{% block dashboard_content %}
<div class="row">
    <div class="col-md-12">
        <canvas id="statsChart"></canvas>
    </div>
</div>

<div class="row mt-4">
    <div class="col-md-12">
        <div class="table-responsive">
            <table class="table table-striped">
                <thead>
                    <tr>
                        <th>ردیف</th>
                        <th>استان</th>
                        <th>تعداد دانشکده</th>
                    </tr>
                </thead>
                <tbody>
                    {% for stat in stats %}
                    <tr>
                        <td>{{ loop.index }}</td>
                        <td>{{ stat.province_name }}</td>
                        <td>{{ stat.count }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
{{ super() }}
<script src="{{ url_for('static', filename='chart.js') }}"></script>
<script>
// Chart initialization
const ctx = document.getElementById('statsChart').getContext('2d');
// ... chart code
</script>
{% endblock %}
```

---

## Responsive Design

### Breakpoints

```css
/* Bootstrap RTL Breakpoints */
@media (max-width: 575.98px) {
    /* Mobile */
}

@media (min-width: 576px) and (max-width: 767.98px) {
    /* Tablet */
}

@media (min-width: 768px) and (max-width: 991.98px) {
    /* Desktop */
}

@media (min-width: 992px) {
    /* Large Desktop */
}
```

### نمونه Responsive Layout

```html
<div class="container-fluid">
    <div class="row">
        <!-- Sidebar: Hidden on mobile -->
        <div class="col-md-3 d-none d-md-block">
            <!-- Filters -->
        </div>
        
        <!-- Main Content: Full width on mobile -->
        <div class="col-md-9 col-12">
            <!-- Dashboard Content -->
        </div>
    </div>
</div>
```

---

## دسترسی‌پذیری (Accessibility)

### اصول دسترسی‌پذیری

1. **Alt Text برای تصاویر**
```html
<img src="..." alt="توضیحات تصویر">
```

2. **Labels برای Input ها**
```html
<label for="input_id">برچسب</label>
<input type="text" id="input_id" name="input_name">
```

3. **ARIA Attributes**
```html
<button aria-label="بستن" aria-expanded="false">
    <span aria-hidden="true">&times;</span>
</button>
```

4. **Keyboard Navigation**
- تمام عناصر قابل دسترسی با کیبورد
- Focus indicators واضح

---

## راهنمای Style Guide

### Typography

```css
/* Font Family */
body {
    font-family: 'Vazir', Tahoma, Arial, sans-serif;
}

/* Headings */
h1 { font-size: 2.5rem; font-weight: bold; }
h2 { font-size: 2rem; font-weight: bold; }
h3 { font-size: 1.75rem; font-weight: bold; }
h4 { font-size: 1.5rem; font-weight: bold; }
h5 { font-size: 1.25rem; font-weight: bold; }
h6 { font-size: 1rem; font-weight: bold; }

/* Body Text */
p { font-size: 1rem; line-height: 1.6; }
```

### Buttons

```html
<!-- Primary Button -->
<button class="btn btn-primary">دکمه اصلی</button>

<!-- Secondary Button -->
<button class="btn btn-secondary">دکمه ثانویه</button>

<!-- Success Button -->
<button class="btn btn-success">موفقیت</button>

<!-- Danger Button -->
<button class="btn btn-danger">خطر</button>
```

### Cards

```html
<div class="card">
    <div class="card-header">
        <h5 class="card-title">عنوان کارت</h5>
    </div>
    <div class="card-body">
        <p class="card-text">محتوای کارت</p>
    </div>
    <div class="card-footer">
        <button class="btn btn-primary">اقدام</button>
    </div>
</div>
```

### Alerts

```html
<div class="alert alert-success" role="alert">
    عملیات با موفقیت انجام شد.
</div>

<div class="alert alert-danger" role="alert">
    خطا در انجام عملیات.
</div>

<div class="alert alert-warning" role="alert">
    هشدار: لطفاً توجه کنید.
</div>

<div class="alert alert-info" role="alert">
    اطلاعات: این یک پیام اطلاعاتی است.
</div>
```

---

## نتیجه‌گیری

این مستند راهنمای کامل UI/UX سیستم است. با دنبال کردن این راهنما، می‌توانید رابط کاربری یکپارچه و کاربرپسندی ایجاد کنید.

---

**تاریخ ایجاد**: 1404/01/15
**نسخه**: 1.0.0
**نگهدارنده**: تیم توسعه

