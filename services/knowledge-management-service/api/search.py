"""
Search API endpoints
"""
import sys
import os
from flask import Blueprint, request, jsonify

# Add parent directory to path for local imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extensions import db
from models import KnowledgeArticle, SearchHistory, Tag, Category
from utils import get_user_id

search_bp = Blueprint('search', __name__)


@search_bp.route('/search', methods=['GET'])
def search():
    """Advanced search for articles"""
    try:
        query = request.args.get('q', '')
        category_id = request.args.get('category_id', type=int)
        tag = request.args.get('tag', '')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        if not query and not tag:
            return jsonify({"error": "Query or tag required", "message": "لطفاً عبارت جستجو یا تگ را وارد کنید"}), 400
        
        # Build query
        search_query = KnowledgeArticle.query.filter_by(status='published')
        
        if query:
            search_query = search_query.filter(
                (KnowledgeArticle.title.contains(query)) |
                (KnowledgeArticle.content.contains(query)) |
                (KnowledgeArticle.summary.contains(query))
            )
        
        if category_id:
            search_query = search_query.filter_by(category_id=category_id)
        
        if tag:
            # Search by tag
            tag_obj = Tag.query.filter_by(name=tag).first()
            if tag_obj:
                article_ids = [at.article_id for at in tag_obj.articles]
                search_query = search_query.filter(KnowledgeArticle.id.in_(article_ids))
        
        search_query = search_query.order_by(KnowledgeArticle.created_at.desc())
        
        pagination = search_query.paginate(page=page, per_page=per_page, error_out=False)
        articles = pagination.items
        
        # Save search history
        if query:
            user_id = get_user_id()
            search_history = SearchHistory(
                user_id=user_id,
                query=query,
                results_count=pagination.total
            )
            db.session.add(search_history)
            db.session.commit()
        
        return jsonify({
            'articles': [article.to_dict() for article in articles],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages,
            'query': query
        }), 200
    except Exception as e:
        return jsonify({"error": str(e), "message": "خطا در جستجو"}), 500


@search_bp.route('/search/suggestions', methods=['GET'])
def search_suggestions():
    """Get search suggestions"""
    try:
        query = request.args.get('q', '')
        
        if not query or len(query) < 2:
            return jsonify({'suggestions': []}), 200
        
        # Get suggestions from article titles
        articles = KnowledgeArticle.query.filter(
            KnowledgeArticle.title.contains(query),
            KnowledgeArticle.status == 'published'
        ).limit(5).all()
        
        suggestions = [article.title for article in articles]
        
        # Get suggestions from tags
        tags = Tag.query.filter(Tag.name.contains(query)).limit(5).all()
        suggestions.extend([tag.name for tag in tags])
        
        return jsonify({'suggestions': suggestions[:10]}), 200
    except Exception as e:
        return jsonify({"error": str(e), "message": "خطا در دریافت پیشنهادات"}), 500

