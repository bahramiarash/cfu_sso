"""
Knowledge Management Service Models
Database models for the knowledge management system
"""
from extensions import db
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, Float
from sqlalchemy.orm import relationship
from typing import Dict, Any

# Note: User model is in auth service, referenced by user_id


class Category(db.Model):
    """Categories for organizing knowledge articles"""
    __tablename__ = 'categories'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    parent_id = Column(Integer, ForeignKey('categories.id'), nullable=True)
    icon = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    parent = relationship('Category', remote_side=[id], backref='children')
    articles = relationship('KnowledgeArticle', back_populates='category')
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'parent_id': self.parent_id,
            'icon': self.icon,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Tag(db.Model):
    """Tags for knowledge articles"""
    __tablename__ = 'tags'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    usage_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    articles = relationship('ArticleTag', back_populates='tag')
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'usage_count': self.usage_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class KnowledgeArticle(db.Model):
    """Knowledge articles - main content"""
    __tablename__ = 'knowledge_articles'
    
    id = Column(Integer, primary_key=True)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    author_id = Column(Integer, nullable=False)  # References users.id in auth service
    category_id = Column(Integer, ForeignKey('categories.id'), nullable=True)
    status = Column(String(20), default='draft', nullable=False)  # draft, published, archived
    views_count = Column(Integer, default=0, nullable=False)
    likes_count = Column(Integer, default=0, nullable=False)
    comments_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    category = relationship('Category', back_populates='articles')
    tags = relationship('ArticleTag', back_populates='article', cascade='all, delete-orphan')
    comments = relationship('Comment', back_populates='article', cascade='all, delete-orphan')
    bookmarks = relationship('Bookmark', back_populates='article', cascade='all, delete-orphan')
    likes = relationship('Like', back_populates='article', cascade='all, delete-orphan')
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'summary': self.summary,
            'author_id': self.author_id,
            'category_id': self.category_id,
            'status': self.status,
            'views_count': self.views_count,
            'likes_count': self.likes_count,
            'comments_count': self.comments_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'tags': [at.tag.to_dict() for at in self.tags],
        }


class ArticleTag(db.Model):
    """Many-to-Many relationship between articles and tags"""
    __tablename__ = 'article_tags'
    
    article_id = Column(Integer, ForeignKey('knowledge_articles.id'), primary_key=True)
    tag_id = Column(Integer, ForeignKey('tags.id'), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    article = relationship('KnowledgeArticle', back_populates='tags')
    tag = relationship('Tag', back_populates='articles')


class Comment(db.Model):
    """Comments on knowledge articles"""
    __tablename__ = 'comments'
    
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey('knowledge_articles.id'), nullable=False)
    user_id = Column(Integer, nullable=False)  # References users.id in auth service
    content = Column(Text, nullable=False)
    parent_id = Column(Integer, ForeignKey('comments.id'), nullable=True)  # For nested comments
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    article = relationship('KnowledgeArticle', back_populates='comments')
    parent = relationship('Comment', remote_side=[id], backref='replies')
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'article_id': self.article_id,
            'user_id': self.user_id,
            'content': self.content,
            'parent_id': self.parent_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Bookmark(db.Model):
    """User bookmarks for articles"""
    __tablename__ = 'bookmarks'
    
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey('knowledge_articles.id'), nullable=False)
    user_id = Column(Integer, nullable=False)  # References users.id in auth service
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    article = relationship('KnowledgeArticle', back_populates='bookmarks')
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'article_id': self.article_id,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Like(db.Model):
    """User likes for articles"""
    __tablename__ = 'likes'
    
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey('knowledge_articles.id'), nullable=False)
    user_id = Column(Integer, nullable=False)  # References users.id in auth service
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    article = relationship('KnowledgeArticle', back_populates='likes')
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'article_id': self.article_id,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Community(db.Model):
    """Communities of Practice"""
    __tablename__ = 'communities'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    creator_id = Column(Integer, nullable=False)  # References users.id in auth service
    member_count = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'creator_id': self.creator_id,
            'member_count': self.member_count,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class LessonLearned(db.Model):
    """Lessons learned from projects"""
    __tablename__ = 'lesson_learned'
    
    id = Column(Integer, primary_key=True)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    project_id = Column(Integer, nullable=True)
    author_id = Column(Integer, nullable=False)  # References users.id in auth service
    tags = Column(JSON, nullable=True)  # Array of tag names
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'project_id': self.project_id,
            'author_id': self.author_id,
            'tags': self.tags,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class SearchHistory(db.Model):
    """User search history for analytics"""
    __tablename__ = 'search_history'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True)  # Null for anonymous searches
    query = Column(String(500), nullable=False)
    results_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'query': self.query,
            'results_count': self.results_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

