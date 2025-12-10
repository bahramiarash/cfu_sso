"""
Survey System Models
Database models for the survey/questionnaire system
"""
from extensions import db
from datetime import datetime
from jdatetime import datetime as jdatetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from typing import Optional, Dict, Any


class SurveyManager(db.Model):
    """Survey Managers - Users authorized to create and manage surveys"""
    __tablename__ = 'survey_managers'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, unique=True)
    is_active = Column(Boolean, default=True, nullable=False)  # Enable/disable manager
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    
    # Relationships
    user = relationship('User', foreign_keys=[user_id], backref='survey_manager_role')
    creator = relationship('User', foreign_keys=[created_by])
    surveys = relationship('Survey', back_populates='manager', cascade='all, delete-orphan')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_name': self.user.name if self.user else None,
            'user_sso_id': self.user.sso_id if self.user else None,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'created_by': self.created_by,
        }


class Survey(db.Model):
    """Surveys/Questionnaires"""
    __tablename__ = 'surveys'
    
    id = Column(Integer, primary_key=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    manager_id = Column(Integer, ForeignKey('survey_managers.id'), nullable=False)
    
    # Date range
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    status = Column(String(20), default='active', nullable=False)  # active, inactive
    
    # Access control
    access_type = Column(String(20), default='public', nullable=False)  # public, user_groups, specific_users, anonymous
    anonymous_access_password = Column(String(255), nullable=True)  # Hashed password for anonymous access (optional)
    
    # Completion limits
    max_completions_per_user = Column(Integer, default=1, nullable=False)
    completion_period_type = Column(String(20), default='yearly', nullable=False)  # monthly, quarterly, semester, yearly
    
    # Welcome page settings
    logo_path = Column(String(500), nullable=True)
    welcome_message = Column(Text, nullable=True)
    welcome_button_text = Column(String(100), default='شروع نظرسنجی', nullable=True)
    
    # Display settings
    display_mode = Column(String(20), default='multi_page', nullable=False)  # single_page, multi_page
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    manager = relationship('SurveyManager', back_populates='surveys')
    categories = relationship('SurveyCategory', back_populates='survey', cascade='all, delete-orphan', order_by='SurveyCategory.order')
    questions = relationship('SurveyQuestion', back_populates='survey', cascade='all, delete-orphan', order_by='SurveyQuestion.order')
    access_groups = relationship('SurveyAccessGroup', back_populates='survey', cascade='all, delete-orphan')
    allowed_users = relationship('SurveyAllowedUser', back_populates='survey', cascade='all, delete-orphan')
    responses = relationship('SurveyResponse', back_populates='survey', cascade='all, delete-orphan')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'manager_id': self.manager_id,
            'manager_name': self.manager.user.name if self.manager and self.manager.user else None,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'status': self.status,
            'access_type': self.access_type,
            'max_completions_per_user': self.max_completions_per_user,
            'completion_period_type': self.completion_period_type,
            'logo_path': self.logo_path,
            'welcome_message': self.welcome_message,
            'welcome_button_text': self.welcome_button_text,
            'display_mode': self.display_mode,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class SurveyAccessGroup(db.Model):
    """User groups allowed to access a survey"""
    __tablename__ = 'survey_access_groups'
    
    id = Column(Integer, primary_key=True)
    survey_id = Column(Integer, ForeignKey('surveys.id'), nullable=False)
    access_level = Column(String(50), nullable=False)  # central_org, province_university, faculty
    
    # Filter restrictions (JSON format)
    # Example: {"province_codes": [1, 2], "university_codes": [10], "faculty_codes": [100]}
    province_codes = Column(JSON, nullable=True)
    university_codes = Column(JSON, nullable=True)
    faculty_codes = Column(JSON, nullable=True)
    
    # Relationships
    survey = relationship('Survey', back_populates='access_groups')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'survey_id': self.survey_id,
            'access_level': self.access_level,
            'province_codes': self.province_codes,
            'university_codes': self.university_codes,
            'faculty_codes': self.faculty_codes,
        }


class SurveyAllowedUser(db.Model):
    """Specific users (by national ID) allowed to access a survey"""
    __tablename__ = 'survey_allowed_users'
    
    id = Column(Integer, primary_key=True)
    survey_id = Column(Integer, ForeignKey('surveys.id'), nullable=False)
    national_id = Column(String(20), nullable=False)  # کد ملی
    
    # Relationships
    survey = relationship('Survey', back_populates='allowed_users')
    
    # Unique constraint: one entry per survey per national_id
    __table_args__ = (
        db.UniqueConstraint('survey_id', 'national_id', name='_survey_national_id_uc'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'survey_id': self.survey_id,
            'national_id': self.national_id,
        }


class SurveyCategory(db.Model):
    """Categories for organizing questions within a survey"""
    __tablename__ = 'survey_categories'
    
    id = Column(Integer, primary_key=True)
    survey_id = Column(Integer, ForeignKey('surveys.id'), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    order = Column(Integer, default=0, nullable=False)
    
    # Relationships
    survey = relationship('Survey', back_populates='categories')
    questions = relationship('SurveyQuestion', back_populates='category', cascade='all, delete-orphan', order_by='SurveyQuestion.order')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'survey_id': self.survey_id,
            'title': self.title,
            'description': self.description,
            'order': self.order,
        }


class SurveyQuestion(db.Model):
    """Questions within a survey"""
    __tablename__ = 'survey_questions'
    
    id = Column(Integer, primary_key=True)
    survey_id = Column(Integer, ForeignKey('surveys.id'), nullable=False)
    category_id = Column(Integer, ForeignKey('survey_categories.id'), nullable=True)
    
    # Question type: likert_2, likert_3, ..., likert_9, text, file_upload
    question_type = Column(String(50), nullable=False)
    question_text = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    order = Column(Integer, default=0, nullable=False)
    is_required = Column(Boolean, default=True, nullable=False)
    
    # Options for Likert scale questions (JSON format)
    # Example: {"options": ["خیلی کم", "کم", "متوسط", "زیاد", "خیلی زیاد"]}
    options = Column(JSON, nullable=True)
    
    # Display type for options: 'radio' (default) or 'dropdown'
    option_display_type = Column(String(20), default='radio', nullable=False)
    
    # Input type for text questions: 'single_line' (input) or 'multi_line' (textarea)
    text_input_type = Column(String(20), default='multi_line', nullable=False)
    
    # Limits for text and file questions
    max_words = Column(Integer, nullable=True)  # Maximum words for text questions (default: 100)
    max_file_size_mb = Column(Integer, nullable=True)  # Maximum file size in MB for file_upload questions (default: 25)
    
    # Relationships
    survey = relationship('Survey', back_populates='questions')
    category = relationship('SurveyCategory', back_populates='questions')
    answer_items = relationship('SurveyAnswerItem', back_populates='question', cascade='all, delete-orphan')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'survey_id': self.survey_id,
            'category_id': self.category_id,
            'category_title': self.category.title if self.category else None,
            'question_type': self.question_type,
            'question_text': self.question_text,
            'description': self.description,
            'order': self.order,
            'is_required': self.is_required,
            'options': self.options,
        }


class SurveyResponse(db.Model):
    """User responses to surveys"""
    __tablename__ = 'survey_responses'
    
    id = Column(Integer, primary_key=True)
    survey_id = Column(Integer, ForeignKey('surveys.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)  # Nullable for anonymous users
    national_id = Column(String(20), nullable=True)  # For users without account
    
    # Status tracking
    is_completed = Column(Boolean, default=False, nullable=False)  # True when finally submitted
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    # Request tracking
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    
    # Completion period tracking (for limiting completions)
    completion_period_key = Column(String(50), nullable=True)  # e.g., "2024-01" for monthly, "2024-Q1" for quarterly
    
    # Relationships
    survey = relationship('Survey', back_populates='responses')
    user = relationship('User', backref='survey_responses')
    answer_items = relationship('SurveyAnswerItem', back_populates='response', cascade='all, delete-orphan')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'survey_id': self.survey_id,
            'user_id': self.user_id,
            'user_name': self.user.name if self.user else None,
            'national_id': self.national_id,
            'is_completed': self.is_completed,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'ip_address': self.ip_address,
            'completion_period_key': self.completion_period_key,
        }


class SurveyAnswerItem(db.Model):
    """Individual answers to questions within a response"""
    __tablename__ = 'survey_answer_items'
    
    id = Column(Integer, primary_key=True)
    response_id = Column(Integer, ForeignKey('survey_responses.id'), nullable=False)
    question_id = Column(Integer, ForeignKey('survey_questions.id'), nullable=False)
    
    # Answer content (depends on question type)
    answer_text = Column(Text, nullable=True)  # For text questions
    answer_value = Column(Integer, nullable=True)  # For Likert scale (0-based index)
    file_path = Column(String(500), nullable=True)  # For file uploads
    
    # Relationships
    response = relationship('SurveyResponse', back_populates='answer_items')
    question = relationship('SurveyQuestion', back_populates='answer_items')
    
    # Unique constraint: one answer per question per response
    __table_args__ = (
        db.UniqueConstraint('response_id', 'question_id', name='_response_question_uc'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'response_id': self.response_id,
            'question_id': self.question_id,
            'question_text': self.question.question_text if self.question else None,
            'question_type': self.question.question_type if self.question else None,
            'answer_text': self.answer_text,
            'answer_value': self.answer_value,
            'file_path': self.file_path,
        }


class SurveyLog(db.Model):
    """Comprehensive logging of all survey-related actions"""
    __tablename__ = 'survey_logs'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    action_type = Column(String(100), nullable=False)  # e.g., 'create_survey', 'submit_response', 'view_report'
    resource_type = Column(String(50), nullable=True)  # e.g., 'survey', 'question', 'response'
    resource_id = Column(Integer, nullable=True)  # ID of the resource
    
    # Request details
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    request_path = Column(String(500), nullable=True)
    request_method = Column(String(10), nullable=True)
    
    # Additional context
    details = Column(JSON, nullable=True)  # Additional context as JSON
    
    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship('User', backref='survey_logs')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        jdate = jdatetime.fromgregorian(datetime=self.created_at) if self.created_at else None
        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_name': self.user.name if self.user else None,
            'action_type': self.action_type,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id,
            'ip_address': self.ip_address,
            'request_path': self.request_path,
            'details': self.details or {},
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'created_at_jalali': jdate.strftime('%Y/%m/%d %H:%M:%S') if jdate else None,
        }

