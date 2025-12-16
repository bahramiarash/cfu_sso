"""
Article API endpoints
"""
import sys
import os
from flask import Blueprint, request, jsonify
from datetime import datetime

# Add parent directory to path for local imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extensions import db
from models import KnowledgeArticle, ArticleTag, Tag, Category
from utils import login_required, get_user_id

articles_bp = Blueprint('articles', __name__)


@articles_bp.route('/articles', methods=['GET'])
def list_articles():
    """List all published articles"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        category_id = request.args.get('category_id', type=int)
        status = request.args.get('status', 'published')
        search = request.args.get('search', '')
        
        query = KnowledgeArticle.query
        
        if status:
            query = query.filter_by(status=status)
        else:
            query = query.filter_by(status='published')
        
        if category_id:
            query = query.filter_by(category_id=category_id)
        
        if search:
            query = query.filter(
                (KnowledgeArticle.title.contains(search)) |
                (KnowledgeArticle.content.contains(search))
            )
        
        query = query.order_by(KnowledgeArticle.created_at.desc())
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        articles = pagination.items
        
        return jsonify({
            'articles': [article.to_dict() for article in articles],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        }), 200
    except Exception as e:
        return jsonify({"error": str(e), "message": "خطا در دریافت مقالات"}), 500


@articles_bp.route('/articles', methods=['POST'])
@login_required
def create_article(user):
    """Create a new article"""
    try:
        data = request.json
        user_id = user.get('id') or get_user_id()
        
        if not user_id:
            return jsonify({"error": "User ID not found", "message": "شناسه کاربر یافت نشد"}), 400
        
        article = KnowledgeArticle(
            title=data.get('title'),
            content=data.get('content'),
            summary=data.get('summary'),
            author_id=user_id,
            category_id=data.get('category_id'),
            status=data.get('status', 'draft')
        )
        
        db.session.add(article)
        db.session.flush()  # Get article ID
        
        # Add tags if provided
        if data.get('tags'):
            for tag_name in data.get('tags', []):
                # Find or create tag
                tag = Tag.query.filter_by(name=tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name)
                    db.session.add(tag)
                    db.session.flush()
                
                # Create article-tag relationship
                article_tag = ArticleTag(article_id=article.id, tag_id=tag.id)
                db.session.add(article_tag)
                tag.usage_count += 1
        
        db.session.commit()
        
        return jsonify(article.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e), "message": "خطا در ایجاد مقاله"}), 500


@articles_bp.route('/articles/<int:article_id>', methods=['GET'])
def get_article(article_id):
    """Get a specific article"""
    try:
        article = KnowledgeArticle.query.get_or_404(article_id)
        
        # Increment view count
        article.views_count += 1
        db.session.commit()
        
        return jsonify(article.to_dict()), 200
    except Exception as e:
        return jsonify({"error": str(e), "message": "خطا در دریافت مقاله"}), 500


@articles_bp.route('/articles/<int:article_id>', methods=['PUT'])
@login_required
def update_article(article_id, user):
    """Update an article"""
    try:
        article = KnowledgeArticle.query.get_or_404(article_id)
        user_id = user.get('id') or get_user_id()
        
        # Check if user is author
        if article.author_id != user_id:
            return jsonify({"error": "Unauthorized", "message": "شما اجازه ویرایش این مقاله را ندارید"}), 403
        
        data = request.json
        
        if 'title' in data:
            article.title = data['title']
        if 'content' in data:
            article.content = data['content']
        if 'summary' in data:
            article.summary = data['summary']
        if 'category_id' in data:
            article.category_id = data['category_id']
        if 'status' in data:
            article.status = data['status']
        
        article.updated_at = datetime.utcnow()
        
        # Update tags if provided
        if 'tags' in data:
            # Remove existing tags
            ArticleTag.query.filter_by(article_id=article.id).delete()
            
            # Add new tags
            for tag_name in data['tags']:
                tag = Tag.query.filter_by(name=tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name)
                    db.session.add(tag)
                    db.session.flush()
                
                article_tag = ArticleTag(article_id=article.id, tag_id=tag.id)
                db.session.add(article_tag)
                tag.usage_count += 1
        
        db.session.commit()
        
        return jsonify(article.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e), "message": "خطا در به‌روزرسانی مقاله"}), 500


@articles_bp.route('/articles/<int:article_id>', methods=['DELETE'])
@login_required
def delete_article(article_id, user):
    """Delete an article"""
    try:
        article = KnowledgeArticle.query.get_or_404(article_id)
        user_id = user.get('id') or get_user_id()
        
        # Check if user is author
        if article.author_id != user_id:
            return jsonify({"error": "Unauthorized", "message": "شما اجازه حذف این مقاله را ندارید"}), 403
        
        db.session.delete(article)
        db.session.commit()
        
        return jsonify({"message": "مقاله با موفقیت حذف شد"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e), "message": "خطا در حذف مقاله"}), 500

