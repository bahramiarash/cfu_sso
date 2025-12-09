"""
Survey System Utilities
Helper functions for survey system
"""
from datetime import datetime
from jdatetime import datetime as jdatetime
from typing import Optional, Dict, Any
from flask import request
from extensions import db
from survey_models import SurveyLog, Survey, SurveyResponse, SurveyManager
from models import User
import logging
import json

logger = logging.getLogger(__name__)


def log_survey_action(action_type: str, resource_type: str = None, resource_id: int = None, 
                      details: dict = None, user_id: int = None):
    """
    Log survey-related action to SurveyLog
    
    Args:
        action_type: Type of action (e.g., 'create_survey', 'submit_response')
        resource_type: Type of resource (e.g., 'survey', 'question', 'response')
        resource_id: ID of resource
        details: Additional context as dictionary
        user_id: Optional user ID (if None, tries to get from request context)
    """
    try:
        if user_id is None:
            # Try to get from current_user if available
            try:
                from flask_login import current_user
                if current_user and current_user.is_authenticated:
                    user_id = current_user.id
            except:
                pass
        
        log_entry = SurveyLog(
            user_id=user_id,
            action_type=action_type,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=request.remote_addr if hasattr(request, 'remote_addr') else None,
            user_agent=request.headers.get('User-Agent') if hasattr(request, 'headers') else None,
            request_path=request.path if hasattr(request, 'path') else None,
            request_method=request.method if hasattr(request, 'method') else None,
            details=details or {}
        )
        
        db.session.add(log_entry)
        db.session.commit()
        
    except Exception as e:
        logger.error(f"Error logging survey action: {e}", exc_info=True)


def sanitize_input(text: str) -> str:
    """
    Sanitize user input to prevent XSS attacks
    
    Args:
        text: Input text to sanitize
        
    Returns:
        Sanitized text
    """
    if not text:
        return ""
    
    # Basic HTML escaping (for more security, use a library like bleach)
    import html
    return html.escape(text)


def validate_file_upload(file) -> tuple[bool, str]:
    """
    Validate uploaded file
    
    Args:
        file: File object from request
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not file:
        return False, "فایل ارسال نشده است"
    
    # Check file size (max 2MB for logos - reasonable size for web images)
    MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB
    file.seek(0, 2)  # Seek to end
    file_size = file.tell()
    file.seek(0)  # Reset to beginning
    
    if file_size > MAX_FILE_SIZE:
        return False, "حجم فایل نباید بیشتر از 2 مگابایت باشد. لطفاً تصویر را فشرده کنید."
    
    # Check file extension
    ALLOWED_EXTENSIONS = {'.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.txt'}
    filename = file.filename.lower() if file.filename else ''
    if not any(filename.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        return False, "نوع فایل مجاز نیست. فایل‌های مجاز: PDF, Word, تصویر, متن"
    
    return True, ""


def check_survey_access(user: User, survey: Survey) -> tuple[bool, str]:
    """
    Check if user has access to a survey
    
    Args:
        user: User object (can be None for anonymous users)
        survey: Survey object
        
    Returns:
        Tuple of (has_access, error_message)
    """
    # Check if survey is active
    if survey.status != 'active':
        return False, "این پرسشنامه در حال حاضر فعال نیست"
    
    # Check date range
    now = datetime.utcnow()
    if survey.start_date is not None and isinstance(survey.start_date, datetime) and now < survey.start_date:
        return False, "این پرسشنامه هنوز شروع نشده است"
    if survey.end_date is not None and isinstance(survey.end_date, datetime) and now > survey.end_date:
        return False, "مهلت تکمیل این پرسشنامه به پایان رسیده است"
    
    # Check access type
    if survey.access_type == 'public':
        return True, ""
    
    elif survey.access_type == 'user_groups':
        # Check if user belongs to any allowed group
        if not user:
            return False, "برای دسترسی به این پرسشنامه نیاز به احراز هویت دارید"
        
        from survey_models import SurveyAccessGroup
        access_groups = SurveyAccessGroup.query.filter_by(survey_id=survey.id).all()
        
        for group in access_groups:
            if group.access_level == 'central_org':
                # Central org - all users have access
                return True, ""
            
            elif group.access_level == 'province_university':
                # Check province and university codes
                if group.province_codes and user.province_code:
                    if user.province_code in group.province_codes:
                        if not group.university_codes or user.university_code in group.university_codes:
                            return True, ""
            
            elif group.access_level == 'faculty':
                # Check faculty codes
                if group.faculty_codes and user.faculty_code:
                    if user.faculty_code in group.faculty_codes:
                        return True, ""
        
        return False, "شما دسترسی به این پرسشنامه ندارید"
    
    elif survey.access_type == 'specific_users':
        # Check if user's national ID is in allowed list
        # Note: We need to get national_id from user_info in session, not from User model
        # This will be handled in the route
        from survey_models import SurveyAllowedUser
        # This check will be done in the route using session data
        return True, ""  # Will be validated in route
    
    return False, "نوع دسترسی نامعتبر"


def check_completion_limit(user: User, survey: Survey, national_id: str = None) -> tuple[bool, str, int]:
    """
    Check if user can complete survey based on completion limits
    
    Args:
        user: User object (can be None for anonymous users)
        survey: Survey object
        national_id: National ID for anonymous users
        
    Returns:
        Tuple of (can_complete, error_message, current_count)
    """
    # Determine identifier
    identifier = user.id if user else None
    identifier_field = 'user_id' if user else 'national_id'
    identifier_value = user.id if user else national_id
    
    if not identifier_value:
        return False, "شناسه کاربری یا کد ملی الزامی است", 0
    
    # Get completion period key
    period_key = get_completion_period_key(survey.completion_period_type)
    
    # Count existing completions in this period
    query = SurveyResponse.query.filter_by(
        survey_id=survey.id,
        completion_period_key=period_key,
        is_completed=True
    )
    
    if user:
        query = query.filter_by(user_id=user.id)
    else:
        query = query.filter_by(national_id=national_id)
    
    current_count = query.count()
    
    if current_count >= survey.max_completions_per_user:
        period_name = {
            'monthly': 'ماه',
            'quarterly': 'فصل',
            'semester': 'ترم',
            'yearly': 'سال'
        }.get(survey.completion_period_type, survey.completion_period_type)
        
        return False, f"شما حداکثر {survey.max_completions_per_user} بار در هر {period_name} می‌توانید این پرسشنامه را تکمیل کنید", current_count
    
    return True, "", current_count


def get_completion_period_key(period_type: str) -> str:
    """
    Get completion period key for tracking
    
    Args:
        period_type: Type of period (monthly, quarterly, semester, yearly)
        
    Returns:
        Period key string (e.g., "2024-01" for monthly)
    """
    now = datetime.utcnow()
    jdate = jdatetime.fromgregorian(datetime=now)
    
    if period_type == 'monthly':
        return f"{jdate.year}-{jdate.month:02d}"
    
    elif period_type == 'quarterly':
        quarter = (jdate.month - 1) // 3 + 1
        return f"{jdate.year}-Q{quarter}"
    
    elif period_type == 'semester':
        # Semester 1: Mehr to Dey (7-10), Semester 2: Bahman to Khordad (11-3), Semester 3: Tir to Shahrivar (4-6)
        month = jdate.month
        if month >= 7 and month <= 10:
            semester = 1
        elif month >= 11 or month <= 3:
            semester = 2
        else:
            semester = 3
        return f"{jdate.year}-S{semester}"
    
    elif period_type == 'yearly':
        return str(jdate.year)
    
    return "unknown"


def calculate_semester_dates() -> Dict[str, datetime]:
    """
    Calculate semester dates based on Jalali calendar
    
    Returns:
        Dictionary with semester start/end dates
    """
    now = datetime.utcnow()
    jdate = jdatetime.fromgregorian(datetime=now)
    
    # Semester 1: Mehr 1 to Dey 29
    # Semester 2: Bahman 1 to Khordad 31
    # Semester 3: Tir 1 to Shahrivar 31
    
    semesters = {}
    
    # Current year
    year = jdate.year
    
    # Semester 1
    sem1_start = jdatetime(year, 7, 1).togregorian()
    sem1_end = jdatetime(year, 10, 29).togregorian()
    semesters['semester_1'] = {'start': sem1_start, 'end': sem1_end}
    
    # Semester 2 (spans year boundary)
    sem2_start = jdatetime(year, 11, 1).togregorian()
    sem2_end = jdatetime(year + 1, 3, 31).togregorian()
    semesters['semester_2'] = {'start': sem2_start, 'end': sem2_end}
    
    # Semester 3
    sem3_start = jdatetime(year, 4, 1).togregorian()
    sem3_end = jdatetime(year, 6, 31).togregorian()
    semesters['semester_3'] = {'start': sem3_start, 'end': sem3_end}
    
    return semesters


def is_survey_manager(user: User) -> bool:
    """
    Check if user is a survey manager
    
    Args:
        user: User object
        
    Returns:
        True if user is an active survey manager
    """
    if not user:
        return False
    
    manager = SurveyManager.query.filter_by(user_id=user.id, is_active=True).first()
    return manager is not None


def get_accessible_surveys(user: User, national_id: str = None) -> list:
    """
    Get all surveys that a user can access (public, user_groups, specific_users)
    
    Args:
        user: User object (can be None)
        national_id: National ID for anonymous users
        
    Returns:
        List of Survey objects that user can access
    """
    from survey_models import Survey, SurveyAccessGroup, SurveyAllowedUser
    from datetime import datetime
    
    now = datetime.utcnow()
    accessible_surveys = []
    
    # Get all active surveys within date range
    all_surveys = Survey.query.filter_by(status='active').filter(
        (Survey.start_date.is_(None) | (Survey.start_date <= now)),
        (Survey.end_date.is_(None) | (Survey.end_date >= now))
    ).all()
    
    for survey in all_surveys:
        # Check if user has access to this survey
        has_access, _ = check_survey_access(user, survey)
        
        if has_access:
            # For specific_users, also check if user's national_id is in allowed list
            if survey.access_type == 'specific_users':
                if national_id:
                    allowed = SurveyAllowedUser.query.filter_by(
                        survey_id=survey.id,
                        national_id=national_id
                    ).first()
                    if allowed:
                        accessible_surveys.append(survey)
                # If no national_id provided, skip this survey
            else:
                # Public or user_groups - already checked by check_survey_access
                accessible_surveys.append(survey)
    
    return accessible_surveys

