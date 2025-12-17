"""
Admin Panel Knowledge Management Routes
Routes for managing knowledge managers and CRUD operations for knowledge articles
"""
import os
import sqlite3
import requests
import json
from flask import render_template, request, jsonify, redirect, url_for, flash, session, current_app
from flask_login import current_user
from werkzeug.utils import secure_filename
from . import admin_bp
from .utils import admin_required, log_action
from models import User, UserType
from admin_models import KnowledgeManager
from extensions import db
from sqlalchemy import desc
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Knowledge Management Service configuration
KNOWLEDGE_SERVICE_URL = os.getenv('KNOWLEDGE_SERVICE_URL', 'http://localhost:5008')
KNOWLEDGE_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'shared', 'databases', 'knowledge.db'
)


def get_knowledge_db_connection():
    """Get connection to knowledge management database"""
    try:
        os.makedirs(os.path.dirname(KNOWLEDGE_DB_PATH), exist_ok=True)
        conn = sqlite3.connect(KNOWLEDGE_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.error(f"Error connecting to knowledge database: {e}", exc_info=True)
        raise


def call_knowledge_api(endpoint, method='GET', data=None, token=None):
    """Call Knowledge Management Service API"""
    try:
        url = f"{KNOWLEDGE_SERVICE_URL}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        
        if method == 'GET':
            response = requests.get(url, headers=headers, timeout=10)
        elif method == 'POST':
            response = requests.post(url, headers=headers, json=data, timeout=10)
        elif method == 'PUT':
            response = requests.put(url, headers=headers, json=data, timeout=10)
        elif method == 'DELETE':
            response = requests.delete(url, headers=headers, timeout=10)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        if response.status_code in [200, 201]:
            return response.json()
        else:
            logger.error(f"API error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"Error calling knowledge API: {e}", exc_info=True)
        return None


# ==================== Knowledge Managers Routes ====================

@admin_bp.route('/knowledge/managers')
@admin_required
def knowledge_managers_list():
    """List all knowledge managers"""
    try:
        managers = db.session.query(KnowledgeManager, User).join(
            User, KnowledgeManager.user_id == User.id
        ).order_by(desc(KnowledgeManager.created_at)).all()
        
        managers_data = []
        for manager, user in managers:
            # Count articles for this manager (from knowledge DB)
            article_count = 0
            try:
                conn = get_knowledge_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM knowledge_articles WHERE author_id = ?",
                    (user.id,)
                )
                result = cursor.fetchone()
                article_count = result[0] if result else 0
                conn.close()
            except Exception as e:
                logger.warning(f"Error counting articles for manager {manager.id}: {e}")
            
            managers_data.append({
                'manager': manager,
                'user': user,
                'article_count': article_count
            })
        
        log_action('view_knowledge_managers', 'knowledge_manager', None)
        return render_template('admin/knowledge/managers/list.html', managers=managers_data)
    except Exception as e:
        logger.error(f"Error listing knowledge managers: {e}", exc_info=True)
        flash('خطا در نمایش لیست مسئولین مدیریت دانش', 'error')
        return redirect(url_for('admin.index'))


@admin_bp.route('/knowledge/managers/create', methods=['GET', 'POST'])
@admin_required
def knowledge_managers_create():
    """Create a new knowledge manager"""
    # Get all users for dropdown
    users = User.query.order_by(User.name).all()
    
    if request.method == 'POST':
        try:
            # Try to get user_id first (from dropdown), then fallback to user_sso_id
            user_id = request.form.get('user_id', '').strip()
            user_sso_id = request.form.get('user_sso_id', '').strip()
            
            user = None
            if user_id:
                try:
                    # Find user by ID
                    user = User.query.get(int(user_id))
                except (ValueError, TypeError):
                    user = None
            if not user and user_sso_id:
                # Find user by SSO ID (backward compatibility)
                user = User.query.filter_by(sso_id=user_sso_id.lower()).first()
            
            if not user:
                flash('لطفاً کاربر را انتخاب کنید', 'error')
                return render_template('admin/knowledge/managers/create.html', users=users)
            
            # Check if user is already a manager
            existing = KnowledgeManager.query.filter_by(user_id=user.id).first()
            if existing:
                flash('این کاربر قبلاً به عنوان مسئول مدیریت دانش تعریف شده است', 'error')
                return render_template('admin/knowledge/managers/create.html', users=users)
            
            # Create new manager
            manager = KnowledgeManager(
                user_id=user.id,
                is_active=True,
                created_by=current_user.id
            )
            db.session.add(manager)
            db.session.commit()
            
            log_action('create_knowledge_manager', 'knowledge_manager', manager.id, {
                'user_id': user.id,
                'user_sso_id': user.sso_id
            })
            flash('مسئول مدیریت دانش با موفقیت ایجاد شد', 'success')
            return redirect(url_for('admin.knowledge_managers_list'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating knowledge manager: {e}", exc_info=True)
            flash('خطا در ایجاد مسئول مدیریت دانش', 'error')
            return render_template('admin/knowledge/managers/create.html', users=users)
    
    return render_template('admin/knowledge/managers/create.html', users=users)


@admin_bp.route('/knowledge/managers/<int:manager_id>/toggle', methods=['POST'])
@admin_required
def knowledge_managers_toggle(manager_id):
    """Toggle active/inactive status of a knowledge manager"""
    try:
        manager = KnowledgeManager.query.get_or_404(manager_id)
        manager.is_active = not manager.is_active
        db.session.commit()
        
        log_action('toggle_knowledge_manager', 'knowledge_manager', manager_id, {
            'is_active': manager.is_active
        })
        
        return jsonify({
            'success': True,
            'is_active': manager.is_active,
            'message': 'وضعیت مسئول مدیریت دانش با موفقیت تغییر کرد'
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error toggling knowledge manager: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': 'خطا در تغییر وضعیت'
        }), 500


@admin_bp.route('/knowledge/managers/<int:manager_id>/delete', methods=['POST'])
@admin_required
def knowledge_managers_delete(manager_id):
    """Delete a knowledge manager"""
    try:
        manager = KnowledgeManager.query.get_or_404(manager_id)
        
        # Check if manager has any articles
        article_count = 0
        try:
            user = User.query.get(manager.user_id)
            if user:
                conn = get_knowledge_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM knowledge_articles WHERE author_id = ?",
                    (user.id,)
                )
                result = cursor.fetchone()
                article_count = result[0] if result else 0
                conn.close()
        except Exception as e:
            logger.warning(f"Error counting articles: {e}")
        
        if article_count > 0:
            return jsonify({
                'success': False,
                'message': f'این مسئول دارای {article_count} مقاله است. ابتدا مقالات را حذف یا منتقل کنید.'
            }), 400
        
        db.session.delete(manager)
        db.session.commit()
        
        log_action('delete_knowledge_manager', 'knowledge_manager', manager_id)
        return jsonify({
            'success': True,
            'message': 'مسئول مدیریت دانش با موفقیت حذف شد'
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting knowledge manager: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': 'خطا در حذف مسئول مدیریت دانش'
        }), 500


# ==================== Articles CRUD Routes (Admin) ====================

@admin_bp.route('/knowledge/articles')
@admin_required
def knowledge_articles_list():
    """List all knowledge articles (admin view)"""
    try:
        conn = get_knowledge_db_connection()
        cursor = conn.cursor()
        
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        search = request.args.get('search', '').strip()
        status = request.args.get('status', '')
        tag_filter = request.args.get('tag', '').strip()
        date_from = request.args.get('date_from', '').strip()
        date_to = request.args.get('date_to', '').strip()
        
        # Build query (without users join - users table is in main DB)
        query = """
            SELECT DISTINCT ka.*, c.name as category_name
            FROM knowledge_articles ka
            LEFT JOIN categories c ON ka.category_id = c.id
            WHERE 1=1
        """
        params = []
        
        if search:
            query += " AND (ka.title LIKE ? OR ka.content LIKE ?)"
            params.extend([f'%{search}%', f'%{search}%'])
        
        if status:
            query += " AND ka.status = ?"
            params.append(status)
        
        # Filter by tag (only user's tags)
        if tag_filter:
            query += """
                AND ka.id IN (
                    SELECT at.article_id
                    FROM article_tags at
                    JOIN tags t ON at.tag_id = t.id
                    WHERE t.name = ? AND ka.author_id = ?
                )
            """
            params.extend([tag_filter, current_user.id])
        
        # Filter by date range (Jalali to Gregorian)
        if date_from:
            try:
                from jdatetime import datetime as jdatetime
                jalali_parts = list(map(int, date_from.split('/')))
                jalali_dt = jdatetime.datetime(jalali_parts[0], jalali_parts[1], jalali_parts[2], 0, 0, 0)
                gregorian_from = jalali_dt.togregorian()
                query += " AND DATE(ka.created_at) >= DATE(?)"
                params.append(gregorian_from.strftime('%Y-%m-%d'))
            except Exception as e:
                logger.warning(f"Error parsing date_from: {e}")
        
        if date_to:
            try:
                from jdatetime import datetime as jdatetime
                jalali_parts = list(map(int, date_to.split('/')))
                jalali_dt = jdatetime.datetime(jalali_parts[0], jalali_parts[1], jalali_parts[2], 23, 59, 59)
                gregorian_to = jalali_dt.togregorian()
                query += " AND DATE(ka.created_at) <= DATE(?)"
                params.append(gregorian_to.strftime('%Y-%m-%d'))
            except Exception as e:
                logger.warning(f"Error parsing date_to: {e}")
        
        query += " ORDER BY ka.created_at DESC"
        
        # Get total count
        count_query = query.replace("SELECT ka.*, c.name as category_name", "SELECT COUNT(*)")
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]
        
        # Get paginated results
        offset = (page - 1) * per_page
        query += " LIMIT ? OFFSET ?"
        params.extend([per_page, offset])
        
        cursor.execute(query, params)
        articles = cursor.fetchall()
        
        # Get user's tags for filter dropdown (before closing connection)
        cursor.execute("""
            SELECT DISTINCT t.name
            FROM tags t
            JOIN article_tags at ON t.id = at.tag_id
            JOIN knowledge_articles ka ON at.article_id = ka.id
            WHERE ka.author_id = ?
            ORDER BY t.name
        """, (current_user.id,))
        user_tags = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        
        # Get author info from main database
        # Convert articles to list of dicts first
        articles_list = [dict(article) for article in articles]
        author_ids = list(set([article['author_id'] for article in articles_list]))
        authors_dict = {}
        if author_ids:
            from models import User
            authors = User.query.filter(User.id.in_(author_ids)).all()
            authors_dict = {author.id: {'name': author.name, 'sso_id': author.sso_id} for author in authors}
        
        # Convert to list of dicts
        articles_data = []
        for article_dict in articles_list:
            author_info = authors_dict.get(article_dict['author_id'], {'name': 'Unknown', 'sso_id': ''})
            articles_data.append({
                'id': article_dict['id'],
                'title': article_dict['title'],
                'summary': article_dict.get('summary', ''),
                'status': article_dict['status'],
                'category_name': article_dict.get('category_name'),
                'author_name': author_info['name'],
                'author_sso_id': author_info['sso_id'],
                'views_count': article_dict.get('views_count', 0),
                'likes_count': article_dict.get('likes_count', 0),
                'created_at': article_dict['created_at'],
                'updated_at': article_dict.get('updated_at'),
            })
        
        total_pages = (total + per_page - 1) // per_page
        
        log_action('view_knowledge_articles', 'knowledge_article', None)
        return render_template('admin/knowledge/articles/list.html',
                             articles=articles_data,
                             page=page,
                             per_page=per_page,
                             total=total,
                             total_pages=total_pages,
                             search=search,
                             status=status,
                             tag_filter=tag_filter,
                             date_from=date_from,
                             date_to=date_to,
                             user_tags=user_tags)
    except Exception as e:
        logger.error(f"Error listing knowledge articles: {e}", exc_info=True)
        flash('خطا در نمایش لیست مقالات', 'error')
        return redirect(url_for('admin.index'))


@admin_bp.route('/knowledge/articles/<int:article_id>/view')
@admin_required
def knowledge_articles_view(article_id):
    """View article details (admin)"""
    try:
        conn = get_knowledge_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT ka.*, c.name as category_name
            FROM knowledge_articles ka
            LEFT JOIN categories c ON ka.category_id = c.id
            WHERE ka.id = ?
        """, (article_id,))
        
        article = cursor.fetchone()
        if not article:
            flash('مقاله یافت نشد', 'error')
            return redirect(url_for('admin.knowledge_articles_list'))
        
        # Get tags
        cursor.execute("""
            SELECT t.name
            FROM tags t
            JOIN article_tags at ON t.id = at.tag_id
            WHERE at.article_id = ?
        """, (article_id,))
        tags = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        
        # Get author info from main database
        from models import User
        # Convert Row to dict for easier access
        article_dict = dict(article)
        author = User.query.get(article_dict['author_id'])
        author_name = author.name if author else 'Unknown'
        author_sso_id = author.sso_id if author else ''
        
        article_data = {
            'id': article_dict['id'],
            'title': article_dict['title'],
            'content': article_dict['content'],
            'summary': article_dict.get('summary', ''),
            'status': article_dict['status'],
            'category_id': article_dict.get('category_id'),
            'category_name': article_dict.get('category_name'),
            'author_id': article_dict['author_id'],
            'author_name': author_name,
            'author_sso_id': author_sso_id,
            'views_count': article_dict.get('views_count', 0),
            'likes_count': article_dict.get('likes_count', 0),
            'comments_count': article_dict.get('comments_count', 0),
            'created_at': article_dict['created_at'],
            'updated_at': article_dict.get('updated_at'),
            'tags': tags
        }
        
        log_action('view_knowledge_article', 'knowledge_article', article_id)
        return render_template('admin/knowledge/articles/view.html', article=article_data)
    except Exception as e:
        logger.error(f"Error viewing article: {e}", exc_info=True)
        flash('خطا در نمایش مقاله', 'error')
        return redirect(url_for('admin.knowledge_articles_list'))


@admin_bp.route('/knowledge/articles/<int:article_id>/edit', methods=['GET', 'POST'])
@admin_required
def knowledge_articles_edit(article_id):
    """Edit article (admin)"""
    try:
        conn = get_knowledge_db_connection()
        cursor = conn.cursor()
        
        if request.method == 'POST':
            try:
                title = request.form.get('title', '').strip()
                content = request.form.get('content', '').strip()
                summary = request.form.get('summary', '').strip()
                category_id = request.form.get('category_id', '') or None
                status = request.form.get('status', 'draft')
                
                # New fields
                access_type = request.form.get('access_type', 'all')
                allowed_user_types = request.form.getlist('allowed_user_types')
                publish_date = request.form.get('publish_date', '').strip() or None
                expiry_date = request.form.get('expiry_date', '').strip() or None
                
                if not title or not content:
                    flash('عنوان و محتوا الزامی است', 'error')
                    return redirect(url_for('admin.knowledge_articles_edit', article_id=article_id))
                
                if category_id:
                    category_id = int(category_id)
                
                # Validate access type
                if access_type == 'user_types' and not allowed_user_types:
                    flash('در صورت انتخاب "انواع کاربری خاص"، حداقل یک نوع کاربری باید انتخاب شود', 'error')
                    return redirect(url_for('admin.knowledge_articles_edit', article_id=article_id))
                
                # Convert allowed_user_types to JSON
                allowed_user_types_json = json.dumps([int(ut) for ut in allowed_user_types]) if allowed_user_types else None
                
                # Update article
                cursor.execute("""
                    UPDATE knowledge_articles
                    SET title = ?, content = ?, summary = ?, category_id = ?, status = ?,
                        access_type = ?, allowed_user_types = ?, publish_date = ?, expiry_date = ?,
                        updated_at = ?
                    WHERE id = ?
                """, (title, content, summary, category_id, status,
                      access_type, allowed_user_types_json, publish_date, expiry_date,
                      datetime.utcnow(), article_id))
                
                # Handle tags
                tags_input = request.form.get('tags', '').strip()
                if tags_input:
                    # Remove existing tags
                    cursor.execute("DELETE FROM article_tags WHERE article_id = ?", (article_id,))
                    
                    # Add new tags
                    tag_names = [t.strip() for t in tags_input.split(',') if t.strip()]
                    for tag_name in tag_names:
                        # Get or create tag
                        cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                        tag_row = cursor.fetchone()
                        if tag_row:
                            tag_id = tag_row[0]
                        else:
                            cursor.execute("INSERT INTO tags (name, usage_count, created_at) VALUES (?, 0, ?)",
                                         (tag_name, datetime.utcnow()))
                            tag_id = cursor.lastrowid
                        
                        # Link article to tag
                        cursor.execute("""
                            INSERT OR IGNORE INTO article_tags (article_id, tag_id, created_at)
                            VALUES (?, ?, ?)
                        """, (article_id, tag_id, datetime.utcnow()))
                
                # Handle file uploads
                if 'attachments' in request.files:
                    files = request.files.getlist('attachments')
                    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'knowledge')
                    os.makedirs(upload_folder, exist_ok=True)
                    
                    allowed_extensions = {'.pdf', '.zip', '.doc', '.docx', '.xls', '.xlsx', 
                                        '.jpg', '.jpeg', '.png', '.ppt', '.pptx'}
                    max_size = 20 * 1024 * 1024  # 20MB
                    
                    for file in files:
                        # Skip empty file inputs
                        if not file or not file.filename or file.filename.strip() == '':
                            continue
                        
                        # Check file extension
                        filename = secure_filename(file.filename)
                        ext = os.path.splitext(filename)[1].lower()
                        
                        if ext not in allowed_extensions:
                            flash(f'فرمت فایل "{filename}" مجاز نیست', 'error')
                            continue
                        
                        # Check file size
                        file.seek(0, os.SEEK_END)
                        file_size = file.tell()
                        file.seek(0)
                        
                        if file_size > max_size:
                            flash(f'فایل "{filename}" بزرگتر از 20MB است', 'error')
                            continue
                        
                        # Save file
                        unique_filename = f"{article_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{filename}"
                        filepath = os.path.join(upload_folder, unique_filename)
                        file.save(filepath)
                        
                        # Get MIME type
                        mime_type = file.content_type or 'application/octet-stream'
                        
                        # Save to database
                        relative_path = os.path.join('static', 'uploads', 'knowledge', unique_filename).replace('\\', '/')
                        cursor.execute("""
                            INSERT INTO article_attachments 
                            (article_id, filename, filepath, file_size, mime_type, created_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (article_id, filename, relative_path, file_size, mime_type, datetime.utcnow()))
                
                conn.commit()
                conn.close()
                
                log_action('edit_knowledge_article', 'knowledge_article', article_id, {'admin_edit': True})
                flash('مقاله با موفقیت به‌روزرسانی شد', 'success')
                return redirect(url_for('admin.knowledge_articles_list'))
                
            except Exception as e:
                conn.rollback()
                conn.close()
                logger.error(f"Error updating article: {e}", exc_info=True)
                flash('خطا در به‌روزرسانی مقاله', 'error')
                return redirect(url_for('admin.knowledge_articles_edit', article_id=article_id))
        
        # GET request - show edit form
        cursor.execute("""
            SELECT ka.*, c.name as category_name
            FROM knowledge_articles ka
            LEFT JOIN categories c ON ka.category_id = c.id
            WHERE ka.id = ?
        """, (article_id,))
        
        article = cursor.fetchone()
        if not article:
            flash('مقاله یافت نشد', 'error')
            return redirect(url_for('admin.knowledge_articles_list'))
        
        # Get tags
        cursor.execute("""
            SELECT t.name
            FROM tags t
            JOIN article_tags at ON t.id = at.tag_id
            WHERE at.article_id = ?
        """, (article_id,))
        tags = [row[0] for row in cursor.fetchall()]
        
        # Get all categories
        cursor.execute("SELECT id, name FROM categories ORDER BY name")
        categories = cursor.fetchall()
        
        # Get existing attachments
        cursor.execute("""
            SELECT id, filename, filepath, file_size, mime_type
            FROM article_attachments
            WHERE article_id = ?
            ORDER BY created_at
        """, (article_id,))
        attachments = cursor.fetchall()
        
        # Get user's previous tags
        cursor.execute("""
            SELECT DISTINCT t.name
            FROM tags t
            JOIN article_tags at ON t.id = at.tag_id
            JOIN knowledge_articles ka ON at.article_id = ka.id
            WHERE ka.author_id = ?
            ORDER BY t.name
        """, (current_user.id,))
        user_tags = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        
        # Convert Row to dict for easier access
        article_dict = dict(article)
        
        # Parse allowed_user_types if exists
        allowed_user_types_list = []
        if article_dict.get('allowed_user_types'):
            try:
                allowed_user_types_list = json.loads(article_dict['allowed_user_types'])
            except:
                allowed_user_types_list = []
        
        article_data = {
            'id': article_dict['id'],
            'title': article_dict['title'],
            'content': article_dict['content'],
            'summary': article_dict.get('summary', ''),
            'status': article_dict['status'],
            'category_id': article_dict.get('category_id'),
            'category_name': article_dict.get('category_name'),
            'tags': ', '.join(tags),
            'access_type': article_dict.get('access_type', 'all'),
            'allowed_user_types': allowed_user_types_list,
            'publish_date': article_dict.get('publish_date'),
            'expiry_date': article_dict.get('expiry_date')
        }
        
        categories_data = [{'id': c['id'], 'name': c['name']} for c in categories]
        attachments_data = [{'id': a['id'], 'filename': a['filename'], 'filepath': a['filepath'], 
                            'file_size': a['file_size'], 'mime_type': a['mime_type']} for a in attachments]
        
        # Get all active user types
        user_types = UserType.query.filter_by(is_active=True).order_by(UserType.name).all()
        
        return render_template('admin/knowledge/articles/edit.html',
                             article=article_data,
                             categories=categories_data,
                             attachments=attachments_data,
                             user_types=user_types,
                             user_tags=user_tags)
    except Exception as e:
        logger.error(f"Error in article edit: {e}", exc_info=True)
        flash('خطا در نمایش فرم ویرایش', 'error')
        return redirect(url_for('admin.knowledge_articles_list'))


@admin_bp.route('/knowledge/articles/create', methods=['GET', 'POST'])
@admin_required
def knowledge_articles_create():
    """Create new article (admin)"""
    try:
        conn = get_knowledge_db_connection()
        cursor = conn.cursor()
        
        if request.method == 'POST':
            try:
                title = request.form.get('title', '').strip()
                content = request.form.get('content', '').strip()
                summary = request.form.get('summary', '').strip()
                category_id = request.form.get('category_id', '') or None
                status = request.form.get('status', 'draft')
                
                # New fields
                access_type = request.form.get('access_type', 'all')
                allowed_user_types = request.form.getlist('allowed_user_types')
                publish_date = request.form.get('publish_date', '').strip() or None
                expiry_date = request.form.get('expiry_date', '').strip() or None
                
                if not title or not content:
                    flash('عنوان و محتوا الزامی است', 'error')
                    return redirect(url_for('admin.knowledge_articles_create'))
                
                if category_id:
                    category_id = int(category_id)
                
                # Validate access type
                if access_type == 'user_types' and not allowed_user_types:
                    flash('در صورت انتخاب "انواع کاربری خاص"، حداقل یک نوع کاربری باید انتخاب شود', 'error')
                    return redirect(url_for('admin.knowledge_articles_create'))
                
                # Convert allowed_user_types to JSON
                allowed_user_types_json = json.dumps([int(ut) for ut in allowed_user_types]) if allowed_user_types else None
                
                # Create article
                cursor.execute("""
                    INSERT INTO knowledge_articles 
                    (title, content, summary, author_id, category_id, status, 
                     access_type, allowed_user_types, publish_date, expiry_date,
                     views_count, likes_count, comments_count,
                     created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (title, content, summary, current_user.id, category_id, status,
                      access_type, allowed_user_types_json, publish_date, expiry_date,
                      0, 0, 0,  # views_count, likes_count, comments_count
                      datetime.utcnow(), datetime.utcnow()))
                
                article_id = cursor.lastrowid
                
                # Handle file uploads
                if 'attachments' in request.files:
                    files = request.files.getlist('attachments')
                    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'knowledge')
                    os.makedirs(upload_folder, exist_ok=True)
                    
                    allowed_extensions = {'.pdf', '.zip', '.doc', '.docx', '.xls', '.xlsx', 
                                        '.jpg', '.jpeg', '.png', '.ppt', '.pptx'}
                    max_size = 20 * 1024 * 1024  # 20MB
                    
                    for file in files:
                        # Skip empty file inputs
                        if not file or not file.filename or file.filename.strip() == '':
                            continue
                        
                        # Check file extension
                        filename = secure_filename(file.filename)
                        ext = os.path.splitext(filename)[1].lower()
                        
                        if ext not in allowed_extensions:
                            flash(f'فرمت فایل "{filename}" مجاز نیست', 'error')
                            continue
                        
                        # Check file size
                        file.seek(0, os.SEEK_END)
                        file_size = file.tell()
                        file.seek(0)
                        
                        if file_size > max_size:
                            flash(f'فایل "{filename}" بزرگتر از 20MB است', 'error')
                            continue
                        
                        # Save file
                        unique_filename = f"{article_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{filename}"
                        filepath = os.path.join(upload_folder, unique_filename)
                        file.save(filepath)
                        
                        # Get MIME type
                        mime_type = file.content_type or 'application/octet-stream'
                        
                        # Save to database
                        relative_path = os.path.join('static', 'uploads', 'knowledge', unique_filename).replace('\\', '/')
                        cursor.execute("""
                            INSERT INTO article_attachments 
                            (article_id, filename, filepath, file_size, mime_type, created_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (article_id, filename, relative_path, file_size, mime_type, datetime.utcnow()))
                
                # Handle tags
                tags_input = request.form.get('tags', '').strip()
                if tags_input:
                    tag_names = [t.strip() for t in tags_input.split(',') if t.strip()]
                    for tag_name in tag_names:
                        # Get or create tag
                        cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                        tag_row = cursor.fetchone()
                        if tag_row:
                            tag_id = tag_row[0]
                        else:
                            cursor.execute("INSERT INTO tags (name, usage_count, created_at) VALUES (?, 0, ?)",
                                         (tag_name, datetime.utcnow()))
                            tag_id = cursor.lastrowid
                        
                        # Link article to tag
                        cursor.execute("""
                            INSERT INTO article_tags (article_id, tag_id, created_at)
                            VALUES (?, ?, ?)
                        """, (article_id, tag_id, datetime.utcnow()))
                
                conn.commit()
                conn.close()
                
                log_action('create_knowledge_article', 'knowledge_article', article_id, {'admin_create': True})
                flash('مقاله با موفقیت ایجاد شد', 'success')
                return redirect(url_for('admin.knowledge_articles_list'))
                
            except Exception as e:
                conn.rollback()
                conn.close()
                logger.error(f"Error creating article: {e}", exc_info=True)
                flash('خطا در ایجاد مقاله', 'error')
                return redirect(url_for('admin.knowledge_articles_create'))
        
        # GET request - show create form
        cursor.execute("SELECT id, name FROM categories ORDER BY name")
        categories = cursor.fetchall()
        
        # Get user's previous tags
        cursor.execute("""
            SELECT DISTINCT t.name
            FROM tags t
            JOIN article_tags at ON t.id = at.tag_id
            JOIN knowledge_articles ka ON at.article_id = ka.id
            WHERE ka.author_id = ?
            ORDER BY t.name
        """, (current_user.id,))
        user_tags = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        
        categories_data = [{'id': c['id'], 'name': c['name']} for c in categories]
        
        # Get all active user types
        user_types = UserType.query.filter_by(is_active=True).order_by(UserType.name).all()
        
        return render_template('admin/knowledge/articles/create.html', 
                             categories=categories_data,
                             user_types=user_types,
                             user_tags=user_tags)
    except Exception as e:
        logger.error(f"Error in article create: {e}", exc_info=True)
        flash('خطا در نمایش فرم ایجاد', 'error')
        return redirect(url_for('admin.knowledge_articles_list'))


@admin_bp.route('/knowledge/articles/user-tags', methods=['GET'])
@admin_required
def knowledge_articles_user_tags():
    """Get user's previous tags for autocomplete"""
    try:
        conn = get_knowledge_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT t.name
            FROM tags t
            JOIN article_tags at ON t.id = at.tag_id
            JOIN knowledge_articles ka ON at.article_id = ka.id
            WHERE ka.author_id = ?
            ORDER BY t.name
        """, (current_user.id,))
        
        tags = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        return jsonify({'tags': tags})
    except Exception as e:
        logger.error(f"Error getting user tags: {e}", exc_info=True)
        return jsonify({'tags': []}), 500


@admin_bp.route('/knowledge/articles/<int:article_id>/attachments/<int:attachment_id>/delete', methods=['POST'])
@admin_required
def knowledge_articles_delete_attachment(article_id, attachment_id):
    """Delete an attachment from an article"""
    try:
        conn = get_knowledge_db_connection()
        cursor = conn.cursor()
        
        # Get attachment info
        cursor.execute("""
            SELECT filepath FROM article_attachments
            WHERE id = ? AND article_id = ?
        """, (attachment_id, article_id))
        
        attachment = cursor.fetchone()
        if not attachment:
            return jsonify({
                'success': False,
                'message': 'فایل یافت نشد'
            }), 404
        
        # Delete file from filesystem
        filepath = attachment['filepath']
        full_path = os.path.join(current_app.root_path, filepath)
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except Exception as e:
                logger.warning(f"Error deleting file {full_path}: {e}")
        
        # Delete from database
        cursor.execute("DELETE FROM article_attachments WHERE id = ?", (attachment_id,))
        conn.commit()
        conn.close()
        
        log_action('delete_article_attachment', 'article_attachment', attachment_id, {
            'article_id': article_id
        })
        
        return jsonify({
            'success': True,
            'message': 'فایل با موفقیت حذف شد'
        })
    except Exception as e:
        conn.rollback()
        conn.close()
        logger.error(f"Error deleting attachment: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': 'خطا در حذف فایل'
        }), 500


@admin_bp.route('/knowledge/articles/<int:article_id>/delete', methods=['POST'])
@admin_required
def knowledge_articles_delete(article_id):
    """Delete article (admin)"""
    try:
        conn = get_knowledge_db_connection()
        cursor = conn.cursor()
        
        # Check if article exists
        cursor.execute("SELECT id FROM knowledge_articles WHERE id = ?", (article_id,))
        if not cursor.fetchone():
            return jsonify({
                'success': False,
                'message': 'مقاله یافت نشد'
            }), 404
        
        # Delete article (cascade will handle related records)
        cursor.execute("DELETE FROM knowledge_articles WHERE id = ?", (article_id,))
        conn.commit()
        conn.close()
        
        log_action('delete_knowledge_article', 'knowledge_article', article_id)
        return jsonify({
            'success': True,
            'message': 'مقاله با موفقیت حذف شد'
        })
    except Exception as e:
        conn.rollback()
        conn.close()
        logger.error(f"Error deleting article: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': 'خطا در حذف مقاله'
        }), 500


# ==================== Categories CRUD Routes (Admin) ====================

@admin_bp.route('/knowledge/categories')
@admin_required
def knowledge_categories_list():
    """List all categories (admin)"""
    try:
        conn = get_knowledge_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT c.*, 
                   COUNT(ka.id) as article_count,
                   (SELECT COUNT(*) FROM categories WHERE parent_id = c.id) as children_count
            FROM categories c
            LEFT JOIN knowledge_articles ka ON c.id = ka.category_id
            GROUP BY c.id
            ORDER BY c.name
        """)
        
        categories = cursor.fetchall()
        conn.close()
        
        categories_data = []
        for cat in categories:
            # Convert Row to dict for easier access
            cat_dict = dict(cat)
            categories_data.append({
                'id': cat_dict['id'],
                'name': cat_dict['name'],
                'description': cat_dict.get('description', ''),
                'parent_id': cat_dict.get('parent_id'),
                'icon': cat_dict.get('icon', ''),
                'article_count': cat_dict['article_count'],
                'children_count': cat_dict['children_count'],
                'created_at': cat_dict['created_at']
            })
        
        log_action('view_knowledge_categories', 'knowledge_category', None)
        return render_template('admin/knowledge/categories/list.html', categories=categories_data)
    except Exception as e:
        logger.error(f"Error listing categories: {e}", exc_info=True)
        flash('خطا در نمایش لیست دسته‌بندی‌ها', 'error')
        return redirect(url_for('admin.index'))


@admin_bp.route('/knowledge/categories/create', methods=['GET', 'POST'])
@admin_required
def knowledge_categories_create():
    """Create new category (admin)"""
    try:
        conn = get_knowledge_db_connection()
        cursor = conn.cursor()
        
        if request.method == 'POST':
            try:
                name = request.form.get('name', '').strip()
                description = request.form.get('description', '').strip()
                parent_id = request.form.get('parent_id', '') or None
                icon = request.form.get('icon', '').strip()
                
                if not name:
                    flash('نام دسته‌بندی الزامی است', 'error')
                    return redirect(url_for('admin.knowledge_categories_create'))
                
                if parent_id:
                    parent_id = int(parent_id)
                
                # Check if name already exists
                cursor.execute("SELECT id FROM categories WHERE name = ?", (name,))
                if cursor.fetchone():
                    flash('دسته‌بندی با این نام قبلاً وجود دارد', 'error')
                    return redirect(url_for('admin.knowledge_categories_create'))
                
                # Create category
                cursor.execute("""
                    INSERT INTO categories (name, description, parent_id, icon, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (name, description, parent_id, icon, datetime.utcnow()))
                
                conn.commit()
                conn.close()
                
                log_action('create_knowledge_category', 'knowledge_category', cursor.lastrowid)
                flash('دسته‌بندی با موفقیت ایجاد شد', 'success')
                return redirect(url_for('admin.knowledge_categories_list'))
                
            except Exception as e:
                conn.rollback()
                conn.close()
                logger.error(f"Error creating category: {e}", exc_info=True)
                flash('خطا در ایجاد دسته‌بندی', 'error')
                return redirect(url_for('admin.knowledge_categories_create'))
        
        # GET request - show create form
        cursor.execute("SELECT id, name FROM categories ORDER BY name")
        parent_categories = cursor.fetchall()
        conn.close()
        
        parent_categories_data = [{'id': c['id'], 'name': c['name']} for c in parent_categories]
        
        return render_template('admin/knowledge/categories/create.html',
                             parent_categories=parent_categories_data)
    except Exception as e:
        logger.error(f"Error in category create: {e}", exc_info=True)
        flash('خطا در نمایش فرم ایجاد', 'error')
        return redirect(url_for('admin.knowledge_categories_list'))


@admin_bp.route('/knowledge/categories/<int:category_id>/edit', methods=['GET', 'POST'])
@admin_required
def knowledge_categories_edit(category_id):
    """Edit category (admin)"""
    try:
        conn = get_knowledge_db_connection()
        cursor = conn.cursor()
        
        if request.method == 'POST':
            try:
                name = request.form.get('name', '').strip()
                description = request.form.get('description', '').strip()
                parent_id = request.form.get('parent_id', '') or None
                icon = request.form.get('icon', '').strip()
                
                if not name:
                    flash('نام دسته‌بندی الزامی است', 'error')
                    return redirect(url_for('admin.knowledge_categories_edit', category_id=category_id))
                
                if parent_id:
                    parent_id = int(parent_id)
                    # Prevent circular reference
                    if parent_id == category_id:
                        flash('دسته‌بندی نمی‌تواند والد خودش باشد', 'error')
                        return redirect(url_for('admin.knowledge_categories_edit', category_id=category_id))
                
                # Check if name already exists (excluding current)
                cursor.execute("SELECT id FROM categories WHERE name = ? AND id != ?", (name, category_id))
                if cursor.fetchone():
                    flash('دسته‌بندی با این نام قبلاً وجود دارد', 'error')
                    return redirect(url_for('admin.knowledge_categories_edit', category_id=category_id))
                
                # Update category
                cursor.execute("""
                    UPDATE categories
                    SET name = ?, description = ?, parent_id = ?, icon = ?
                    WHERE id = ?
                """, (name, description, parent_id, icon, category_id))
                
                conn.commit()
                conn.close()
                
                log_action('edit_knowledge_category', 'knowledge_category', category_id)
                flash('دسته‌بندی با موفقیت به‌روزرسانی شد', 'success')
                return redirect(url_for('admin.knowledge_categories_list'))
                
            except Exception as e:
                conn.rollback()
                conn.close()
                logger.error(f"Error updating category: {e}", exc_info=True)
                flash('خطا در به‌روزرسانی دسته‌بندی', 'error')
                return redirect(url_for('admin.knowledge_categories_edit', category_id=category_id))
        
        # GET request - show edit form
        cursor.execute("SELECT * FROM categories WHERE id = ?", (category_id,))
        category = cursor.fetchone()
        if not category:
            flash('دسته‌بندی یافت نشد', 'error')
            return redirect(url_for('admin.knowledge_categories_list'))
        
        cursor.execute("SELECT id, name FROM categories WHERE id != ? ORDER BY name", (category_id,))
        parent_categories = cursor.fetchall()
        conn.close()
        
        # Convert Row to dict for easier access
        category_dict = dict(category)
        category_data = {
            'id': category_dict['id'],
            'name': category_dict['name'],
            'description': category_dict.get('description', ''),
            'parent_id': category_dict.get('parent_id'),
            'icon': category_dict.get('icon', '')
        }
        
        parent_categories_data = [{'id': c['id'], 'name': c['name']} for c in parent_categories]
        
        return render_template('admin/knowledge/categories/edit.html',
                             category=category_data,
                             parent_categories=parent_categories_data)
    except Exception as e:
        logger.error(f"Error in category edit: {e}", exc_info=True)
        flash('خطا در نمایش فرم ویرایش', 'error')
        return redirect(url_for('admin.knowledge_categories_list'))


@admin_bp.route('/knowledge/categories/<int:category_id>/delete', methods=['POST'])
@admin_required
def knowledge_categories_delete(category_id):
    """Delete category (admin)"""
    try:
        conn = get_knowledge_db_connection()
        cursor = conn.cursor()
        
        # Check if category exists
        cursor.execute("SELECT id FROM categories WHERE id = ?", (category_id,))
        if not cursor.fetchone():
            return jsonify({
                'success': False,
                'message': 'دسته‌بندی یافت نشد'
            }), 404
        
        # Check if category has articles
        cursor.execute("SELECT COUNT(*) FROM knowledge_articles WHERE category_id = ?", (category_id,))
        article_count = cursor.fetchone()[0]
        
        # Check if category has children
        cursor.execute("SELECT COUNT(*) FROM categories WHERE parent_id = ?", (category_id,))
        children_count = cursor.fetchone()[0]
        
        if article_count > 0 or children_count > 0:
            return jsonify({
                'success': False,
                'message': f'این دسته‌بندی دارای {article_count} مقاله و {children_count} زیردسته است. ابتدا آنها را حذف یا منتقل کنید.'
            }), 400
        
        # Delete category
        cursor.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        conn.commit()
        conn.close()
        
        log_action('delete_knowledge_category', 'knowledge_category', category_id)
        return jsonify({
            'success': True,
            'message': 'دسته‌بندی با موفقیت حذف شد'
        })
    except Exception as e:
        conn.rollback()
        conn.close()
        logger.error(f"Error deleting category: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': 'خطا در حذف دسته‌بندی'
        }), 500

