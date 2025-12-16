"""
Category API endpoints
"""
import sys
import os
from flask import Blueprint, request, jsonify

# Add parent directory to path for local imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extensions import db
from models import Category
from utils import login_required

categories_bp = Blueprint('categories', __name__)


@categories_bp.route('/categories', methods=['GET'])
def list_categories():
    """List all categories"""
    try:
        categories = Category.query.all()
        return jsonify({
            'categories': [cat.to_dict() for cat in categories]
        }), 200
    except Exception as e:
        return jsonify({"error": str(e), "message": "خطا در دریافت دسته‌بندی‌ها"}), 500


@categories_bp.route('/categories', methods=['POST'])
@login_required
def create_category(user):
    """Create a new category"""
    try:
        data = request.json
        
        category = Category(
            name=data.get('name'),
            description=data.get('description'),
            parent_id=data.get('parent_id'),
            icon=data.get('icon')
        )
        
        db.session.add(category)
        db.session.commit()
        
        return jsonify(category.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e), "message": "خطا در ایجاد دسته‌بندی"}), 500

