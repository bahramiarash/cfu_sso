"""
Analytics API endpoints
"""
import sys
import os
from flask import Blueprint, request, jsonify
from sqlalchemy import func

# Add parent directory to path for local imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extensions import db
from models import KnowledgeArticle, SearchHistory, Tag
from utils import login_required

analytics_bp = Blueprint('analytics', __name__)


@analytics_bp.route('/analytics/usage', methods=['GET'])
@login_required
def usage_analytics(user):
    """Get usage analytics"""
    try:
        # Total articles
        total_articles = KnowledgeArticle.query.count()
        published_articles = KnowledgeArticle.query.filter_by(status='published').count()
        
        # Total views
        total_views = db.session.query(func.sum(KnowledgeArticle.views_count)).scalar() or 0
        
        # Total searches
        total_searches = SearchHistory.query.count()
        
        # Most viewed articles
        most_viewed = KnowledgeArticle.query.filter_by(status='published').order_by(
            KnowledgeArticle.views_count.desc()
        ).limit(10).all()
        
        return jsonify({
            'total_articles': total_articles,
            'published_articles': published_articles,
            'total_views': total_views,
            'total_searches': total_searches,
            'most_viewed': [article.to_dict() for article in most_viewed]
        }), 200
    except Exception as e:
        return jsonify({"error": str(e), "message": "خطا در دریافت آمار"}), 500


@analytics_bp.route('/analytics/popular', methods=['GET'])
def popular_content():
    """Get popular content"""
    try:
        # Most liked articles
        most_liked = KnowledgeArticle.query.filter_by(status='published').order_by(
            KnowledgeArticle.likes_count.desc()
        ).limit(10).all()
        
        # Most commented articles
        most_commented = KnowledgeArticle.query.filter_by(status='published').order_by(
            KnowledgeArticle.comments_count.desc()
        ).limit(10).all()
        
        # Popular tags
        popular_tags = Tag.query.order_by(Tag.usage_count.desc()).limit(10).all()
        
        return jsonify({
            'most_liked': [article.to_dict() for article in most_liked],
            'most_commented': [article.to_dict() for article in most_commented],
            'popular_tags': [tag.to_dict() for tag in popular_tags]
        }), 200
    except Exception as e:
        return jsonify({"error": str(e), "message": "خطا در دریافت محتوای محبوب"}), 500

