"""
Knowledge Management Service
Main Flask application
"""
import os
import sys
import logging
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
from extensions import db
from models import (
    Category, Tag, KnowledgeArticle, ArticleTag, Comment,
    Bookmark, Like, Community, LessonLearned, SearchHistory
)

# Add current directory to path first (for local imports)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Add shared directory to path (for shared utilities)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

# Load environment variables
BASE_DIR_ENV = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR_ENV))
load_dotenv(dotenv_path=os.path.join(PROJECT_ROOT, '.env'))
load_dotenv(dotenv_path=os.path.join(BASE_DIR_ENV, '.env'))
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Database configuration
DB_PATH = os.path.join(PROJECT_ROOT, 'shared', 'databases', 'knowledge.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{DB_PATH}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Initialize extensions
db.init_app(app)

# Register blueprints
from api.articles import articles_bp
from api.categories import categories_bp
from api.search import search_bp
from api.ai import ai_bp
from api.analytics import analytics_bp

app.register_blueprint(articles_bp, url_prefix='/api/knowledge')
app.register_blueprint(categories_bp, url_prefix='/api/knowledge')
app.register_blueprint(search_bp, url_prefix='/api/knowledge')
app.register_blueprint(ai_bp, url_prefix='/api/knowledge')
app.register_blueprint(analytics_bp, url_prefix='/api/knowledge')


@app.route("/health")
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "knowledge-management-service"}), 200


@app.route("/")
def index():
    """Service information or HTML page"""
    # Check if request wants HTML (browser request)
    # Check Accept header first
    accept_header = request.headers.get('Accept', '').lower()
    user_agent = request.headers.get('User-Agent', '').lower()
    
    logger.info(f"Knowledge service / request - Accept: {accept_header[:100]}, User-Agent: {user_agent[:50]}")
    
    # Determine if this is a browser request
    # Browsers typically send Accept: text/html,application/xhtml+xml,...
    is_browser = (
        'text/html' in accept_header or
        user_agent.startswith('mozilla') or
        'chrome' in user_agent or
        'firefox' in user_agent or
        'safari' in user_agent or
        'edge' in user_agent
    )
    
    # Also check if it's a direct browser navigation (not API call)
    # API calls usually have Accept: application/json
    is_api_call = 'application/json' in accept_header and 'text/html' not in accept_header
    
    logger.info(f"Knowledge service - is_browser: {is_browser}, is_api_call: {is_api_call}")
    
    if is_browser and not is_api_call:
        logger.info("Returning HTML page for browser request")
        # Return a complete HTML page
        html_content = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>سامانه مدیریت دانش - دانشگاه فرهنگیان</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">
    <style>
        body {
            font-family: "Vazir", Tahoma, Arial, sans-serif;
            background-color: #f8f9fa;
            padding-top: 20px;
        }
        .main-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 2rem 0;
            margin-bottom: 2rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .card {
            transition: transform 0.2s, box-shadow 0.2s;
            margin-bottom: 1.5rem;
        }
        .card:hover {
            transform: translateY(-5px);
            box-shadow: 0 8px 20px rgba(0,0,0,0.15);
        }
        .card-icon {
            font-size: 3rem;
            margin-bottom: 1rem;
        }
        .api-section {
            background: white;
            padding: 2rem;
            border-radius: 8px;
            margin-top: 2rem;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
    </style>
</head>
<body>
    <div class="main-header">
        <div class="container">
            <h1 class="text-center mb-0">
                <i class="bi bi-book"></i> سامانه مدیریت دانش
            </h1>
            <p class="text-center mt-2 mb-0">دانشگاه فرهنگیان</p>
        </div>
    </div>
    
    <div class="container">
        <div class="row">
            <div class="col-md-4">
                <div class="card text-center">
                    <div class="card-body">
                        <div class="card-icon">📚</div>
                        <h5 class="card-title">مقالات دانش</h5>
                        <p class="card-text">مدیریت و مشاهده مقالات دانش</p>
                        <a href="/knowledge/articles" class="btn btn-primary">مشاهده مقالات</a>
                    </div>
                </div>
            </div>
            
            <div class="col-md-4">
                <div class="card text-center">
                    <div class="card-body">
                        <div class="card-icon">📁</div>
                        <h5 class="card-title">دسته‌بندی‌ها</h5>
                        <p class="card-text">مدیریت دسته‌بندی‌های دانش</p>
                        <a href="/knowledge/categories" class="btn btn-primary">مشاهده دسته‌بندی‌ها</a>
                    </div>
                </div>
            </div>
            
            <div class="col-md-4">
                <div class="card text-center">
                    <div class="card-body">
                        <div class="card-icon">🔍</div>
                        <h5 class="card-title">جستجو</h5>
                        <p class="card-text">جستجوی پیشرفته در محتوا</p>
                        <a href="/knowledge/search" class="btn btn-primary">جستجو</a>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="api-section">
            <h3><i class="bi bi-code-slash"></i> API Endpoints</h3>
            <hr>
            <div class="row">
                <div class="col-md-6">
                    <h5>مقالات</h5>
                    <ul>
                        <li><code>GET /api/knowledge/articles</code> - لیست مقالات</li>
                        <li><code>POST /api/knowledge/articles</code> - ایجاد مقاله</li>
                        <li><code>GET /api/knowledge/articles/:id</code> - دریافت مقاله</li>
                    </ul>
                </div>
                <div class="col-md-6">
                    <h5>جستجو و دسته‌بندی</h5>
                    <ul>
                        <li><code>GET /api/knowledge/search</code> - جستجوی پیشرفته</li>
                        <li><code>GET /api/knowledge/categories</code> - لیست دسته‌بندی‌ها</li>
                        <li><code>GET /api/knowledge/analytics/usage</code> - آمار استفاده</li>
                    </ul>
                </div>
            </div>
        </div>
        
        <div class="text-center mt-4">
            <a href="/tools" class="btn btn-secondary">
                <i class="bi bi-arrow-right"></i> بازگشت به صفحه اصلی
            </a>
        </div>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>"""
        from flask import Response
        response = Response(html_content, mimetype='text/html', status=200)
        return response
    
    # Otherwise return JSON for API requests
    return jsonify({
        "service": "Knowledge Management Service",
        "version": "1.0.0",
        "status": "running"
    }), 200


@app.route("/articles")
def articles_page():
    """HTML page for articles list"""
    html_content = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>مقالات دانش - سامانه مدیریت دانش</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">
    <style>
        body { font-family: "Vazir", Tahoma, Arial, sans-serif; background-color: #f8f9fa; padding-top: 20px; }
        .main-header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem 0; margin-bottom: 2rem; }
        .article-card { margin-bottom: 1.5rem; transition: transform 0.2s; }
        .article-card:hover { transform: translateY(-3px); }
        .loading { text-align: center; padding: 2rem; }
    </style>
</head>
<body>
    <div class="main-header">
        <div class="container">
            <h1 class="text-center mb-0"><i class="bi bi-book"></i> مقالات دانش</h1>
            <p class="text-center mt-2 mb-0">دانشگاه فرهنگیان</p>
        </div>
    </div>
    
    <div class="container">
        <div class="d-flex justify-content-between align-items-center mb-4">
            <h2>لیست مقالات</h2>
            <a href="/knowledge" class="btn btn-secondary"><i class="bi bi-arrow-right"></i> بازگشت</a>
        </div>
        
        <div id="loading" class="loading">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">در حال بارگذاری...</span>
            </div>
            <p class="mt-2">در حال بارگذاری مقالات...</p>
        </div>
        
        <div id="articles-container" style="display: none;">
            <div id="articles-list"></div>
            <div id="pagination" class="mt-4"></div>
        </div>
        
        <div id="error-message" class="alert alert-danger" style="display: none;"></div>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        let currentPage = 1;
        
        async function loadArticles(page = 1) {
            document.getElementById('loading').style.display = 'block';
            document.getElementById('articles-container').style.display = 'none';
            document.getElementById('error-message').style.display = 'none';
            
            try {
                const response = await fetch(`/knowledge/api/knowledge/articles?page=${page}&per_page=10`);
                const data = await response.json();
                
                if (response.ok) {
                    displayArticles(data.articles || []);
                    displayPagination(data.page || 1, data.pages || 1, data.total || 0);
                    document.getElementById('loading').style.display = 'none';
                    document.getElementById('articles-container').style.display = 'block';
                } else {
                    throw new Error(data.message || 'خطا در دریافت مقالات');
                }
            } catch (error) {
                document.getElementById('loading').style.display = 'none';
                document.getElementById('error-message').textContent = 'خطا: ' + error.message;
                document.getElementById('error-message').style.display = 'block';
            }
        }
        
        function displayArticles(articles) {
            const container = document.getElementById('articles-list');
            if (articles.length === 0) {
                container.innerHTML = '<div class="alert alert-info">هنوز مقاله‌ای ثبت نشده است.</div>';
                return;
            }
            
            container.innerHTML = articles.map(article => `
                <div class="card article-card">
                    <div class="card-body">
                        <h5 class="card-title">${escapeHtml(article.title || 'بدون عنوان')}</h5>
                        <p class="card-text">${escapeHtml((article.summary || article.content || '').substring(0, 200))}...</p>
                        <div class="d-flex justify-content-between align-items-center">
                            <small class="text-muted">
                                <i class="bi bi-eye"></i> ${article.views_count || 0} بازدید
                                <i class="bi bi-heart ms-2"></i> ${article.likes_count || 0} لایک
                            </small>
                            <a href="/knowledge/api/knowledge/articles/${article.id}" class="btn btn-sm btn-primary">مشاهده کامل</a>
                        </div>
                    </div>
                </div>
            `).join('');
        }
        
        function displayPagination(page, pages, total) {
            const container = document.getElementById('pagination');
            if (pages <= 1) {
                container.innerHTML = '';
                return;
            }
            
            let html = '<nav><ul class="pagination justify-content-center">';
            
            if (page > 1) {
                html += `<li class="page-item"><a class="page-link" href="#" onclick="loadArticles(${page - 1}); return false;">قبلی</a></li>`;
            }
            
            for (let i = 1; i <= pages; i++) {
                if (i === page) {
                    html += `<li class="page-item active"><span class="page-link">${i}</span></li>`;
                } else {
                    html += `<li class="page-item"><a class="page-link" href="#" onclick="loadArticles(${i}); return false;">${i}</a></li>`;
                }
            }
            
            if (page < pages) {
                html += `<li class="page-item"><a class="page-link" href="#" onclick="loadArticles(${page + 1}); return false;">بعدی</a></li>`;
            }
            
            html += '</ul></nav>';
            html += `<p class="text-center text-muted">مجموع ${total} مقاله</p>`;
            container.innerHTML = html;
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        // Load articles on page load
        loadArticles(1);
    </script>
</body>
</html>"""
    from flask import Response
    return Response(html_content, mimetype='text/html', status=200)


@app.route("/categories")
def categories_page():
    """HTML page for categories list"""
    html_content = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>دسته‌بندی‌ها - سامانه مدیریت دانش</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">
    <style>
        body { font-family: "Vazir", Tahoma, Arial, sans-serif; background-color: #f8f9fa; padding-top: 20px; }
        .main-header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem 0; margin-bottom: 2rem; }
        .category-card { margin-bottom: 1.5rem; transition: transform 0.2s; }
        .category-card:hover { transform: translateY(-3px); }
        .loading { text-align: center; padding: 2rem; }
    </style>
</head>
<body>
    <div class="main-header">
        <div class="container">
            <h1 class="text-center mb-0"><i class="bi bi-folder"></i> دسته‌بندی‌ها</h1>
            <p class="text-center mt-2 mb-0">دانشگاه فرهنگیان</p>
        </div>
    </div>
    
    <div class="container">
        <div class="d-flex justify-content-between align-items-center mb-4">
            <h2>لیست دسته‌بندی‌ها</h2>
            <a href="/knowledge" class="btn btn-secondary"><i class="bi bi-arrow-right"></i> بازگشت</a>
        </div>
        
        <div id="loading" class="loading">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">در حال بارگذاری...</span>
            </div>
            <p class="mt-2">در حال بارگذاری دسته‌بندی‌ها...</p>
        </div>
        
        <div id="categories-container" style="display: none;">
            <div id="categories-list" class="row"></div>
        </div>
        
        <div id="error-message" class="alert alert-danger" style="display: none;"></div>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        async function loadCategories() {
            document.getElementById('loading').style.display = 'block';
            document.getElementById('categories-container').style.display = 'none';
            document.getElementById('error-message').style.display = 'none';
            
            try {
                const response = await fetch('/knowledge/api/knowledge/categories');
                const data = await response.json();
                
                if (response.ok) {
                    displayCategories(data.categories || []);
                    document.getElementById('loading').style.display = 'none';
                    document.getElementById('categories-container').style.display = 'block';
                } else {
                    throw new Error(data.message || 'خطا در دریافت دسته‌بندی‌ها');
                }
            } catch (error) {
                document.getElementById('loading').style.display = 'none';
                document.getElementById('error-message').textContent = 'خطا: ' + error.message;
                document.getElementById('error-message').style.display = 'block';
            }
        }
        
        function displayCategories(categories) {
            const container = document.getElementById('categories-list');
            if (categories.length === 0) {
                container.innerHTML = '<div class="alert alert-info">هنوز دسته‌بندی‌ای ثبت نشده است.</div>';
                return;
            }
            
            container.innerHTML = categories.map(cat => `
                <div class="col-md-4 mb-3">
                    <div class="card category-card h-100">
                        <div class="card-body">
                            <h5 class="card-title"><i class="bi bi-folder-fill"></i> ${escapeHtml(cat.name || 'بدون نام')}</h5>
                            <p class="card-text">${escapeHtml(cat.description || 'بدون توضیحات')}</p>
                        </div>
                    </div>
                </div>
            `).join('');
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        // Load categories on page load
        loadCategories();
    </script>
</body>
</html>"""
    from flask import Response
    return Response(html_content, mimetype='text/html', status=200)


@app.route("/search")
def search_page():
    """HTML page for search"""
    html_content = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>جستجو - سامانه مدیریت دانش</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">
    <style>
        body { font-family: "Vazir", Tahoma, Arial, sans-serif; background-color: #f8f9fa; padding-top: 20px; }
        .main-header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2rem 0; margin-bottom: 2rem; }
        .search-box { max-width: 600px; margin: 0 auto 2rem; }
        .result-card { margin-bottom: 1.5rem; transition: transform 0.2s; }
        .result-card:hover { transform: translateY(-3px); }
        .loading { text-align: center; padding: 2rem; display: none; }
    </style>
</head>
<body>
    <div class="main-header">
        <div class="container">
            <h1 class="text-center mb-0"><i class="bi bi-search"></i> جستجوی پیشرفته</h1>
            <p class="text-center mt-2 mb-0">دانشگاه فرهنگیان</p>
        </div>
    </div>
    
    <div class="container">
        <div class="d-flex justify-content-between align-items-center mb-4">
            <h2>جستجو در مقالات</h2>
            <a href="/knowledge" class="btn btn-secondary"><i class="bi bi-arrow-right"></i> بازگشت</a>
        </div>
        
        <div class="search-box">
            <div class="input-group input-group-lg">
                <input type="text" id="search-input" class="form-control" placeholder="عبارت جستجو را وارد کنید..." onkeypress="if(event.key === 'Enter') performSearch()">
                <button class="btn btn-primary" onclick="performSearch()">
                    <i class="bi bi-search"></i> جستجو
                </button>
            </div>
        </div>
        
        <div id="loading" class="loading">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">در حال جستجو...</span>
            </div>
            <p class="mt-2">در حال جستجو...</p>
        </div>
        
        <div id="results-container" style="display: none;">
            <div id="results-info" class="mb-3"></div>
            <div id="results-list"></div>
            <div id="pagination" class="mt-4"></div>
        </div>
        
        <div id="error-message" class="alert alert-danger" style="display: none;"></div>
        
        <div id="empty-state" class="text-center text-muted" style="display: block;">
            <i class="bi bi-search" style="font-size: 4rem; opacity: 0.3;"></i>
            <p class="mt-3">برای شروع جستجو، عبارت مورد نظر را وارد کنید</p>
        </div>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        let currentPage = 1;
        let currentQuery = '';
        
        async function performSearch(page = 1) {
            const query = document.getElementById('search-input').value.trim();
            
            if (!query) {
                alert('لطفاً عبارت جستجو را وارد کنید');
                return;
            }
            
            currentQuery = query;
            currentPage = page;
            
            document.getElementById('loading').style.display = 'block';
            document.getElementById('results-container').style.display = 'none';
            document.getElementById('error-message').style.display = 'none';
            document.getElementById('empty-state').style.display = 'none';
            
            try {
                const response = await fetch(`/knowledge/api/knowledge/search?q=${encodeURIComponent(query)}&page=${page}&per_page=10`);
                const data = await response.json();
                
                if (response.ok) {
                    displayResults(data.articles || [], data.total || 0, data.page || 1, data.pages || 1);
                    document.getElementById('loading').style.display = 'none';
                    document.getElementById('results-container').style.display = 'block';
                } else {
                    throw new Error(data.message || 'خطا در جستجو');
                }
            } catch (error) {
                document.getElementById('loading').style.display = 'none';
                document.getElementById('error-message').textContent = 'خطا: ' + error.message;
                document.getElementById('error-message').style.display = 'block';
            }
        }
        
        function displayResults(articles, total, page, pages) {
            const infoContainer = document.getElementById('results-info');
            const listContainer = document.getElementById('results-list');
            
            infoContainer.innerHTML = `<p class="text-muted">نتایج جستجو برای "${escapeHtml(currentQuery)}": ${total} مقاله یافت شد</p>`;
            
            if (articles.length === 0) {
                listContainer.innerHTML = '<div class="alert alert-info">نتیجه‌ای یافت نشد.</div>';
                document.getElementById('pagination').innerHTML = '';
                return;
            }
            
            listContainer.innerHTML = articles.map(article => `
                <div class="card result-card">
                    <div class="card-body">
                        <h5 class="card-title">${escapeHtml(article.title || 'بدون عنوان')}</h5>
                        <p class="card-text">${escapeHtml((article.summary || article.content || '').substring(0, 200))}...</p>
                        <div class="d-flex justify-content-between align-items-center">
                            <small class="text-muted">
                                <i class="bi bi-eye"></i> ${article.views_count || 0} بازدید
                                <i class="bi bi-heart ms-2"></i> ${article.likes_count || 0} لایک
                            </small>
                            <a href="/knowledge/api/knowledge/articles/${article.id}" class="btn btn-sm btn-primary">مشاهده کامل</a>
                        </div>
                    </div>
                </div>
            `).join('');
            
            // Pagination
            const paginationContainer = document.getElementById('pagination');
            if (pages <= 1) {
                paginationContainer.innerHTML = '';
                return;
            }
            
            let html = '<nav><ul class="pagination justify-content-center">';
            if (page > 1) {
                html += `<li class="page-item"><a class="page-link" href="#" onclick="performSearch(${page - 1}); return false;">قبلی</a></li>`;
            }
            for (let i = 1; i <= pages; i++) {
                if (i === page) {
                    html += `<li class="page-item active"><span class="page-link">${i}</span></li>`;
                } else {
                    html += `<li class="page-item"><a class="page-link" href="#" onclick="performSearch(${i}); return false;">${i}</a></li>`;
                }
            }
            if (page < pages) {
                html += `<li class="page-item"><a class="page-link" href="#" onclick="performSearch(${page + 1}); return false;">بعدی</a></li>`;
            }
            html += '</ul></nav>';
            paginationContainer.innerHTML = html;
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    </script>
</body>
</html>"""
    from flask import Response
    return Response(html_content, mimetype='text/html', status=200)


# Initialize database
with app.app_context():
    db.create_all()
    logger.info("Database initialized")


if __name__ == "__main__":
    import socket
    
    # Check if port is already in use
    port = 5008
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()
    if result == 0:
        logger.error(f"Port {port} is already in use. Please stop the existing service first.")
        sys.exit(1)
    
    logger.info(f"Starting Knowledge Management Service on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)

