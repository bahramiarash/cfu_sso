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


def validate_file_upload(file, max_size_mb: int = None, allowed_extensions: set = None) -> tuple[bool, str]:
    """
    Validate uploaded file
    
    Args:
        file: File object from request
        max_size_mb: Maximum file size in MB (optional, defaults to 2MB for backward compatibility)
        allowed_extensions: Set of allowed file extensions (optional, defaults to common file types)
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not file:
        return False, "فایل ارسال نشده است"
    
    # Get filename first (before any file operations)
    filename = getattr(file, 'filename', None) or ''
    # Strip whitespace and check if it's actually empty
    filename = filename.strip() if filename else ''
    if not filename:
        # Return True for empty files (they should be handled by the caller)
        # This allows optional file uploads to work correctly
        return True, ""
    
    # Check file extension first (before file operations that might affect the file object)
    if allowed_extensions is None:
        ALLOWED_EXTENSIONS = {'.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.txt'}
    else:
        ALLOWED_EXTENSIONS = allowed_extensions
    
    # Extract extension properly
    filename_lower = filename.lower().strip()
    # Get extension with dot
    if '.' in filename_lower:
        file_ext = '.' + filename_lower.rsplit('.', 1)[1].strip()
    else:
        file_ext = ''
    
    if file_ext not in ALLOWED_EXTENSIONS:
        allowed_list = ', '.join(sorted([ext.replace('.', '').upper() for ext in ALLOWED_EXTENSIONS]))
        return False, f"نوع فایل مجاز نیست. فایل‌های مجاز: {allowed_list}"
    
    # Check file size (use provided max_size_mb or default to 2MB for backward compatibility)
    max_size_bytes = (max_size_mb * 1024 * 1024) if max_size_mb else (2 * 1024 * 1024)
    try:
        file.seek(0, 2)  # Seek to end
        file_size = file.tell()
        file.seek(0)  # Reset to beginning
    except Exception as e:
        # If we can't read file size, still allow the upload but log the error
        import logging
        logging.getLogger(__name__).warning(f"Could not read file size for {filename}: {e}")
        file_size = 0  # Assume it's valid if we can't check
    
    if file_size > max_size_bytes:
        max_size_display = max_size_mb if max_size_mb else 2
        return False, f"حجم فایل نباید بیشتر از {max_size_display} مگابایت باشد."
    
    return True, ""


def validate_logo_upload(file, max_size_mb: int = 2) -> tuple[bool, str]:
    """
    Validate uploaded logo file (images only)
    
    Args:
        file: File object from request
        max_size_mb: Maximum file size in MB (defaults to 2MB)
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # CRITICAL: Check if file is empty or has no filename first
    if not file:
        return True, ""  # Empty file is valid (optional upload)
    
    # Get filename and check if it's empty
    filename = getattr(file, 'filename', None) or ''
    filename = filename.strip() if filename else ''
    if not filename:
        # Empty filename means no file was uploaded - this is valid for optional uploads
        return True, ""
    
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp'}
    
    # Debug: log filename for troubleshooting
    filename_lower = filename.lower()
    if '.' in filename_lower:
        file_ext = '.' + filename_lower.rsplit('.', 1)[1]
        logger.debug(f"Validating logo file: {filename}, extracted extension: {file_ext}")
        if file_ext not in image_extensions:
            logger.warning(f"Logo file extension {file_ext} not in allowed extensions: {image_extensions}")
    else:
        logger.warning(f"Logo file {filename} has no extension")
    
    return validate_file_upload(file, max_size_mb=max_size_mb, allowed_extensions=image_extensions)


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
    
    elif survey.access_type == 'anonymous':
        # Anonymous access - no authentication required
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
    Uses UserType to identify survey managers instead of SurveyManager table
    
    Args:
        user: User object
        
    Returns:
        True if user has "مسئول نظرسنجی" user type
    """
    if not user:
        return False
    
    # Check if user has "مسئول نظرسنجی" user type
    from models import UserType
    survey_manager_type = UserType.query.filter_by(name='مسئول نظرسنجی').first()
    if not survey_manager_type:
        return False
    
    return survey_manager_type in user.user_types


def get_survey_manager_id(user: User) -> Optional[int]:
    """
    Get SurveyManager ID for a user
    Creates SurveyManager record if it doesn't exist and user has the type
    
    Args:
        user: User object
        
    Returns:
        SurveyManager ID if user is a survey manager, None otherwise
    """
    manager = get_survey_manager(user)
    return manager.id if manager else None


def get_survey_manager(user: User) -> Optional[SurveyManager]:
    """
    Get SurveyManager object for a user
    Creates SurveyManager record if it doesn't exist and user has the type
    
    Args:
        user: User object
        
    Returns:
        SurveyManager object if user is a survey manager, None otherwise
    """
    if not user:
        return None
    
    # Check if user has "مسئول نظرسنجی" user type
    from models import UserType
    survey_manager_type = UserType.query.filter_by(name='مسئول نظرسنجی').first()
    if not survey_manager_type:
        return None
    
    if survey_manager_type not in user.user_types:
        return None
    
    # Get or create SurveyManager record
    manager = SurveyManager.query.filter_by(user_id=user.id).first()
    if not manager:
        # Create SurveyManager record if it doesn't exist
        manager = SurveyManager(
            user_id=user.id,
            is_active=True
        )
        db.session.add(manager)
        db.session.commit()
    
    return manager


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


def get_user_survey_status(user: User, survey_id: int, national_id: str = None) -> Dict[str, Any]:
    """
    Get user's completion status for a survey
    
    Args:
        user: User object (can be None)
        survey_id: Survey ID
        national_id: National ID for anonymous users
        
    Returns:
        Dictionary with status information:
        - 'status': 'completed', 'started', 'not_started'
        - 'completed_count': Number of completed responses
        - 'last_completed_at': Last completion datetime (if any)
        - 'last_started_at': Last start datetime (if any)
    """
    if not user and not national_id:
        return {'status': 'not_started', 'completed_count': 0}
    
    # Query for responses
    query = SurveyResponse.query.filter_by(survey_id=survey_id)
    
    if user:
        query = query.filter_by(user_id=user.id)
    elif national_id:
        query = query.filter_by(national_id=national_id)
    else:
        return {'status': 'not_started', 'completed_count': 0}
    
    # Get all responses
    all_responses = query.order_by(SurveyResponse.started_at.desc()).all()
    
    if not all_responses:
        return {'status': 'not_started', 'completed_count': 0, 'last_started_at': None, 'last_completed_at': None}
    
    # Check for completed responses
    completed_responses = [r for r in all_responses if r.is_completed]
    
    if completed_responses:
        return {
            'status': 'completed',
            'completed_count': len(completed_responses),
            'last_completed_at': completed_responses[0].completed_at if completed_responses[0].completed_at else None,
            'last_started_at': all_responses[0].started_at if all_responses else None
        }
    
    # Check for started but not completed
    started_responses = [r for r in all_responses if not r.is_completed]
    
    if started_responses:
        return {
            'status': 'started',
            'completed_count': 0,
            'last_started_at': started_responses[0].started_at if started_responses else None,
            'last_completed_at': None
        }
    
    return {'status': 'not_started', 'completed_count': 0, 'last_started_at': None, 'last_completed_at': None}


def validate_national_id(national_id: str) -> tuple[bool, str]:
    """
    Validate Iranian national ID (کد ملی)
    
    Args:
        national_id: National ID string
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not national_id:
        return False, "کد ملی نمی‌تواند خالی باشد"
    
    # Remove any spaces or dashes
    national_id = national_id.strip().replace(' ', '').replace('-', '')
    
    # Check if it's exactly 10 digits
    if not national_id.isdigit():
        return False, "کد ملی باید فقط شامل اعداد باشد"
    
    if len(national_id) != 10:
        return False, "کد ملی باید دقیقاً 10 رقم باشد"
    
    # Iranian national ID validation algorithm
    # Check digit is calculated based on first 9 digits
    check_digit = int(national_id[9])
    sum_digits = 0
    
    for i in range(9):
        sum_digits += int(national_id[i]) * (10 - i)
    
    remainder = sum_digits % 11
    
    # Check digit should be remainder if remainder < 2, otherwise 11 - remainder
    expected_check = remainder if remainder < 2 else 11 - remainder
    
    if check_digit != expected_check:
        return False, "کد ملی وارد شده معتبر نیست"
    
    return True, ""


def validate_email(email: str) -> tuple[bool, str]:
    """
    Validate email format
    
    Args:
        email: Email string
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not email:
        return False, "ایمیل نمی‌تواند خالی باشد"
    
    email = email.strip()
    
    # Basic email validation regex
    import re
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(email_pattern, email):
        return False, "فرمت ایمیل وارد شده معتبر نیست"
    
    return True, ""


def validate_landline_phone(phone: str) -> tuple[bool, str]:
    """
    Validate Iranian landline phone number (تلفن ثابت)
    
    Args:
        phone: Phone number string
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not phone:
        return False, "شماره تلفن ثابت نمی‌تواند خالی باشد"
    
    # Remove any spaces, dashes, or parentheses
    phone = phone.strip().replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    
    # Remove country code if present
    if phone.startswith('0098'):
        phone = phone[4:]
    elif phone.startswith('+98'):
        phone = phone[3:]
    elif phone.startswith('098'):
        phone = phone[3:]
    elif phone.startswith('98'):
        phone = phone[2:]
    
    # Check if it's all digits
    if not phone.isdigit():
        return False, "شماره تلفن ثابت باید فقط شامل اعداد باشد"
    
    # Iranian landline numbers are typically 11 digits (with area code) or 8 digits (local)
    # Area codes are 2-3 digits, local numbers are 7-8 digits
    # Common format: 0XX-XXXXXXX (11 digits total with leading 0)
    if phone.startswith('0'):
        phone = phone[1:]  # Remove leading 0
    
    # Check length (should be 10 digits after removing leading 0)
    if len(phone) < 8 or len(phone) > 10:
        return False, "شماره تلفن ثابت باید بین 8 تا 10 رقم باشد (بدون کد کشور)"
    
    # Check if area code is valid (Iranian area codes are typically 2-3 digits)
    # This is a basic check - you might want to add more specific validation
    return True, ""


def validate_mobile_phone(phone: str) -> tuple[bool, str]:
    """
    Validate Iranian mobile phone number (تلفن همراه)
    
    Args:
        phone: Phone number string
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not phone:
        return False, "شماره تلفن همراه نمی‌تواند خالی باشد"
    
    # Remove any spaces, dashes, or parentheses
    phone = phone.strip().replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    
    # Remove country code if present
    if phone.startswith('0098'):
        phone = phone[4:]
    elif phone.startswith('+98'):
        phone = phone[3:]
    elif phone.startswith('098'):
        phone = phone[3:]
    elif phone.startswith('98'):
        phone = phone[2:]
    
    # Check if it's all digits
    if not phone.isdigit():
        return False, "شماره تلفن همراه باید فقط شامل اعداد باشد"
    
    # Iranian mobile numbers should start with 09 and be 11 digits total
    # Or 10 digits without leading 0
    if phone.startswith('0'):
        phone = phone[1:]  # Remove leading 0
    
    # Check length (should be 10 digits after removing leading 0)
    if len(phone) != 10:
        return False, "شماره تلفن همراه باید 10 رقم باشد (بدون کد کشور و صفر ابتدایی)"
    
    # Iranian mobile numbers start with 9
    if not phone.startswith('9'):
        return False, "شماره تلفن همراه باید با 9 شروع شود"
    
    # Check if it's a valid mobile prefix (091x, 092x, 093x, 094x, 095x, 096x, 097x, 098x, 099x)
    valid_prefixes = ['91', '92', '93', '94', '95', '96', '97', '98', '99']
    prefix = phone[:2]
    
    if prefix not in valid_prefixes:
        return False, "پیش‌شماره تلفن همراه معتبر نیست"
    
    return True, ""


def validate_website(url: str) -> tuple[bool, str]:
    """
    Validate website URL format
    
    Args:
        url: Website URL string
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not url:
        return False, "نشانی وب سایت نمی‌تواند خالی باشد"
    
    url = url.strip()
    
    # Add http:// if no protocol is specified
    if not url.startswith(('http://', 'https://', 'www.')):
        url = 'http://' + url
    
    # Basic URL validation
    import re
    url_pattern = r'^https?://(?:[-\w.])+(?:\:[0-9]+)?(?:/(?:[\w/_.])*)?(?:\?(?:[\w&=%.])*)?(?:#(?:[\w.])*)?$'
    
    if not re.match(url_pattern, url):
        return False, "فرمت نشانی وب سایت معتبر نیست"
    
    return True, ""


def validate_answer_by_type(answer_text: str, validation_type: str) -> tuple[bool, str]:
    """
    Validate answer text based on validation type
    
    Args:
        answer_text: Answer text to validate
        validation_type: Type of validation ('none', 'national_id', 'email', 'landline', 'mobile', 'website')
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not validation_type or validation_type == 'none' or validation_type == '':
        return True, ""  # No validation required
    
    if validation_type == 'national_id':
        return validate_national_id(answer_text)
    elif validation_type == 'email':
        return validate_email(answer_text)
    elif validation_type == 'landline':
        return validate_landline_phone(answer_text)
    elif validation_type == 'mobile':
        return validate_mobile_phone(answer_text)
    elif validation_type == 'website':
        return validate_website(answer_text)
    else:
        # Unknown validation type - allow it
        return True, ""
