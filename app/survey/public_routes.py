"""
Public Survey Routes
Routes for users to complete surveys
"""
from flask import render_template, request, jsonify, redirect, url_for, flash, session, make_response
from flask_login import current_user
from auth_utils import requires_auth
from functools import wraps
from . import survey_bp
from .utils import (
    log_survey_action, check_survey_access, check_completion_limit, 
    sanitize_input, get_completion_period_key, validate_answer_by_type
)
from models import User
from survey_models import (
    Survey, SurveyResponse, SurveyAnswerItem, SurveyQuestion, 
    SurveyCategory, SurveyAllowedUser, SurveyManager,
    SurveyParameter, SurveyResponseParameter
)
from extensions import db
from datetime import datetime
from sqlalchemy import desc
import logging
import json
import hashlib

logger = logging.getLogger(__name__)

# Secret key for generating anonymous access hash
ANONYMOUS_ACCESS_SECRET = "cfu_survey_anonymous_2024"


def generate_anonymous_access_hash(survey_id):
    """
    Generate a hash for anonymous survey access
    
    Args:
        survey_id: Survey ID
        
    Returns:
        Hash string
    """
    data = f"{survey_id}_{ANONYMOUS_ACCESS_SECRET}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def verify_anonymous_access_hash(survey_id, hash_value):
    """
    Verify if the hash is valid for the survey
    
    Args:
        survey_id: Survey ID
        hash_value: Hash to verify
        
    Returns:
        True if hash is valid, False otherwise
    """
    expected_hash = generate_anonymous_access_hash(survey_id)
    return hash_value == expected_hash


def requires_auth_or_anonymous(f):
    """
    Decorator that requires authentication unless survey has anonymous access with valid hash
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # Check if survey_id is in kwargs
        survey_id = kwargs.get('survey_id')
        if survey_id:
            survey = Survey.query.get(survey_id)
            if survey and survey.access_type == 'anonymous':
                # Check for hash in query string or session
                hash_param = request.args.get('hash')
                hash_in_session = session.get(f'anonymous_survey_{survey_id}')
                
                logger.info(f"Anonymous survey access check: survey_id={survey_id}, hash_param={hash_param[:8] if hash_param else 'None'}..., hash_in_session={hash_in_session[:8] if hash_in_session else 'None'}..., path={request.path}")
                
                # If hash is in query string, verify it
                if hash_param:
                    if verify_anonymous_access_hash(survey_id, hash_param):
                        # Valid hash - store in session and allow access
                        session[f'anonymous_survey_{survey_id}'] = hash_param
                        logger.info(f"Valid hash found in query string, allowing access")
                        return f(*args, **kwargs)
                    else:
                        # Invalid hash - redirect to survey list
                        logger.warning(f"Invalid hash in query string: {hash_param[:8]}...")
                        flash('لینک دسترسی نامعتبر است', 'error')
                        return redirect(url_for('survey'))
                
                # If hash is in session (from previous request), allow access
                if hash_in_session:
                    if verify_anonymous_access_hash(survey_id, hash_in_session):
                        logger.info(f"Valid hash found in session, allowing access")
                        return f(*args, **kwargs)
                    else:
                        # Invalid hash in session - clear it and redirect
                        logger.warning(f"Invalid hash in session: {hash_in_session[:8]}...")
                        session.pop(f'anonymous_survey_{survey_id}', None)
                        flash('لینک دسترسی نامعتبر است', 'error')
                        return redirect(url_for('survey'))
                
                # Anonymous survey but no hash - redirect to survey list
                logger.warning(f"Anonymous survey but no hash found in query string or session")
                flash('لینک دسترسی نامعتبر است', 'error')
                return redirect(url_for('survey'))
        
        # For other cases, require authentication
        if "sso_token" not in session:
            logger.info(f"User not authenticated, redirecting to login. survey_id={survey_id}, path={request.path}")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated

def get_user_display_name_from_session():
    """Get user display name from session"""
    user_info = session.get("user_info")
    if not user_info:
        return "کاربر گرامی"
    
    if user_info.get('fullname'):
        return user_info.get('fullname')
    
    firstname = user_info.get('firstname', '')
    lastname = user_info.get('lastname', '')
    if firstname or lastname:
        return f"{firstname} {lastname}".strip()
    
    return user_info.get('name') or user_info.get('username') or "کاربر گرامی"


@survey_bp.route('/<int:survey_id>/anonymous/password', methods=['GET', 'POST'])
def survey_anonymous_password(survey_id):
    """Password entry page for anonymous surveys with password protection"""
    try:
        survey = Survey.query.get_or_404(survey_id)
        
        # Check if survey is anonymous and requires password
        if survey.access_type != 'anonymous' or not survey.anonymous_access_password:
            flash('این پرسشنامه نیاز به رمز ندارد', 'error')
            return redirect(url_for('survey'))
        
        hash_param = request.args.get('hash')
        if not hash_param or not verify_anonymous_access_hash(survey_id, hash_param):
            flash('لینک دسترسی نامعتبر است', 'error')
            return redirect(url_for('survey'))
        
        if request.method == 'POST':
            entered_password = request.form.get('password', '').strip()
            if not entered_password:
                flash('لطفاً رمز را وارد کنید', 'error')
                return render_template('survey/public/anonymous_password.html', 
                                     survey=survey, 
                                     hash=hash_param)
            
            # Verify password
            import hashlib
            entered_password_hash = hashlib.sha256(entered_password.encode()).hexdigest()
            
            if entered_password_hash == survey.anonymous_access_password:
                # Password is correct - store in session and redirect to survey
                session[f'anonymous_survey_{survey_id}_password_verified'] = True
                session[f'anonymous_survey_{survey_id}'] = hash_param
                return redirect(url_for('survey.survey_start', survey_id=survey_id, hash=hash_param))
            else:
                flash('رمز وارد شده اشتباه است', 'error')
                return render_template('survey/public/anonymous_password.html', 
                                     survey=survey, 
                                     hash=hash_param)
        
        # GET request - show password entry form
        return render_template('survey/public/anonymous_password.html', 
                             survey=survey, 
                             hash=hash_param)
    except Exception as e:
        logger.error(f"Error in survey_anonymous_password: {e}", exc_info=True)
        return render_template('error.html', error=f"خطا: {str(e)}"), 500


@survey_bp.route('/<int:survey_id>/start')
@requires_auth_or_anonymous
def survey_start(survey_id):
    """Start survey - welcome page with access check"""
    try:
        survey = Survey.query.get_or_404(survey_id)
        
        # Check if this is an anonymous access via hash
        hash_param = request.args.get('hash')
        hash_in_session = session.get(f'anonymous_survey_{survey_id}')
        is_anonymous_access = False
        password_verified = False
        
        # Use hash from query string if available, otherwise from session
        active_hash = hash_param or hash_in_session
        
        if active_hash and survey.access_type == 'anonymous':
            if verify_anonymous_access_hash(survey_id, active_hash):
                # Check if password is required
                if survey.anonymous_access_password:
                    # Password is required - check if it's already verified in session
                    password_verified = session.get(f'anonymous_survey_{survey_id}_password_verified', False)
                    
                    if not password_verified:
                        # Redirect to password entry page
                        return redirect(url_for('survey.survey_anonymous_password', survey_id=survey_id, hash=active_hash))
                else:
                    # No password required
                    password_verified = True
                    is_anonymous_access = True
                    # Store hash in session for subsequent requests
                    session[f'anonymous_survey_{survey_id}'] = active_hash
                    # Update hash_param to use active_hash for template
                    hash_param = active_hash
            else:
                flash('لینک دسترسی نامعتبر است', 'error')
                return redirect(url_for('survey'))
        elif survey.access_type == 'anonymous' and not active_hash:
            # Anonymous survey but no hash - redirect to survey list
            flash('لینک دسترسی نامعتبر است', 'error')
            return redirect(url_for('survey'))
        
        # If password is verified, set anonymous access
        if password_verified:
            is_anonymous_access = True
            session[f'anonymous_survey_{survey_id}'] = active_hash
            # Update hash_param to use active_hash for template
            hash_param = active_hash
            
            # Store URL parameters in session for anonymous surveys
            if survey.access_type == 'anonymous':
                # Get all defined parameters for this survey
                survey_parameters = SurveyParameter.query.filter_by(survey_id=survey_id).all()
                parameter_dict = {}
                
                for param in survey_parameters:
                    param_value = request.args.get(param.parameter_name)
                    if param_value:
                        # Validate that the value is in the allowed list
                        if param_value in param.parameter_values:
                            parameter_dict[param.parameter_name] = param_value
                
                # Store parameters in session
                if parameter_dict:
                    session[f'anonymous_survey_{survey_id}_parameters'] = parameter_dict
        
        # Check if survey is active
        if survey.status != 'active':
            flash('این پرسشنامه در حال حاضر فعال نیست', 'error')
            return redirect(url_for('survey'))
        
        # Check date range
        now = datetime.utcnow()
        if survey.start_date is not None and isinstance(survey.start_date, datetime) and now < survey.start_date:
            flash('این پرسشنامه هنوز شروع نشده است', 'error')
            return redirect(url_for('survey'))
        if survey.end_date is not None and isinstance(survey.end_date, datetime) and now > survey.end_date:
            flash('مهلت تکمیل این پرسشنامه به پایان رسیده است', 'error')
            return redirect(url_for('survey'))
        
        # Get user info (skip for anonymous access)
        user_info = session.get("user_info") if not is_anonymous_access else None
        username = user_info.get('username', '').lower() if user_info else None
        user = User.query.filter_by(sso_id=username).first() if username else None
        national_id = user_info.get('national_id') if user_info else None
        
        # Check if user is the survey manager (managers can always access their own surveys)
        is_manager_owner = False
        if user:
            from survey.utils import is_survey_manager
            if is_survey_manager(user):
                manager = SurveyManager.query.filter_by(user_id=user.id, is_active=True).first()
                if manager and survey.manager_id == manager.id:
                    is_manager_owner = True
        
        # Check access (skip for manager owners and anonymous access)
        if not is_manager_owner and not is_anonymous_access:
            has_access, error_msg = check_survey_access(user, survey)
            if not has_access:
                # For specific_users access type, check national_id
                if survey.access_type == 'specific_users':
                    if not national_id:
                        flash('برای دسترسی به این پرسشنامه، لطفاً کد ملی خود را وارد کنید', 'error')
                        return render_template('survey/public/enter_national_id.html', survey=survey)
                    
                    allowed = SurveyAllowedUser.query.filter_by(
                        survey_id=survey_id,
                        national_id=national_id
                    ).first()
                    if not allowed:
                        flash('شما دسترسی به این پرسشنامه ندارید', 'error')
                        return redirect(url_for('survey'))
                else:
                    flash(error_msg or 'شما دسترسی به این پرسشنامه ندارید', 'error')
                    return redirect(url_for('survey'))
        
        # Check completion limit (skip for manager owners and anonymous access)
        if not is_manager_owner and not is_anonymous_access:
            can_complete, limit_msg, current_count = check_completion_limit(user, survey, national_id)
            if not can_complete:
                flash(limit_msg, 'error')
                return redirect(url_for('survey'))
        elif is_anonymous_access:
            # For anonymous access, we can't track by user, so we'll allow completion
            # but track by IP or session
            can_complete = True
            limit_msg = ""
            current_count = 0
        
        display_name = get_user_display_name_from_session() if not is_anonymous_access else "کاربر گرامی"
        
        # Get hash for passing to template (for anonymous surveys)
        hash_for_template = hash_param if is_anonymous_access else None
        
        log_survey_action('view_survey_welcome', 'survey', survey_id)
        return render_template('survey/public/welcome.html', 
                             survey=survey,
                             user_display_name=display_name,
                             hash_param=hash_for_template)
    except Exception as e:
        logger.error(f"Error in survey_start: {e}", exc_info=True)
        return render_template('error.html', error=f"خطا در بارگذاری نظرسنجی: {str(e)}"), 500


@survey_bp.route('/<int:survey_id>/questions', methods=['GET', 'POST'])
@requires_auth_or_anonymous
def survey_questions(survey_id):
    """Display survey questions and handle submission"""
    try:
        survey = Survey.query.get_or_404(survey_id)
        
        # Check if this is an anonymous access via hash (from session or referrer)
        is_anonymous_access = False
        if survey.access_type == 'anonymous':
            # Check if hash is in session (set from survey_start)
            hash_in_session = session.get(f'anonymous_survey_{survey_id}')
            hash_param = request.args.get('hash')
            
            # Check if password is required and verified
            password_verified = session.get(f'anonymous_survey_{survey_id}_password_verified', False)
            
            if hash_param and verify_anonymous_access_hash(survey_id, hash_param):
                if survey.anonymous_access_password:
                    # Password is required - check if verified
                    if password_verified:
                        is_anonymous_access = True
                        session[f'anonymous_survey_{survey_id}'] = hash_param
                    else:
                        # Password not verified - redirect to password page
                        return redirect(url_for('survey.survey_anonymous_password', survey_id=survey_id, hash=hash_param))
                else:
                    # No password required
                    is_anonymous_access = True
                    session[f'anonymous_survey_{survey_id}'] = hash_param
            elif hash_in_session and verify_anonymous_access_hash(survey_id, hash_in_session):
                if survey.anonymous_access_password:
                    if password_verified:
                        is_anonymous_access = True
                    else:
                        # Need to verify password
                        return redirect(url_for('survey.survey_anonymous_password', survey_id=survey_id, hash=hash_in_session))
                else:
                    is_anonymous_access = True
            
            # Store URL parameters in session for anonymous surveys
            if is_anonymous_access and survey.access_type == 'anonymous':
                # Get all defined parameters for this survey
                survey_parameters = SurveyParameter.query.filter_by(survey_id=survey_id).all()
                parameter_dict = {}
                
                for param in survey_parameters:
                    param_value = request.args.get(param.parameter_name)
                    if param_value:
                        # Validate that the value is in the allowed list
                        if param_value in param.parameter_values:
                            parameter_dict[param.parameter_name] = param_value
                
                # Store parameters in session (update if already exists)
                if parameter_dict:
                    session[f'anonymous_survey_{survey_id}_parameters'] = parameter_dict
        
        # Check if survey is active
        if survey.status != 'active':
            flash('این پرسشنامه در حال حاضر فعال نیست', 'error')
            return redirect(url_for('survey'))
        
        # Get user info (skip for anonymous access)
        user_info = session.get("user_info") if not is_anonymous_access else None
        username = user_info.get('username', '').lower() if user_info else None
        user = User.query.filter_by(sso_id=username).first() if username else None
        national_id = user_info.get('national_id') if user_info else None
        
        if request.method == 'POST':
            # Handle form submission
            return handle_survey_submission(survey_id, survey, user, national_id, is_anonymous_access)
        
        # GET request - display questions
        # Get all questions ordered by category and order
        categories = SurveyCategory.query.filter_by(survey_id=survey_id).order_by(SurveyCategory.order).all()
        questions = SurveyQuestion.query.filter_by(survey_id=survey_id).order_by(
            SurveyQuestion.order
        ).all()
        
        # Group questions by category
        questions_by_category = {}
        questions_without_category = []
        
        for question in questions:
            if question.category_id:
                if question.category_id not in questions_by_category:
                    questions_by_category[question.category_id] = []
                questions_by_category[question.category_id].append(question)
            else:
                questions_without_category.append(question)
        
        display_name = get_user_display_name_from_session() if not is_anonymous_access else "کاربر گرامی"
        
        log_survey_action('view_survey_questions', 'survey', survey_id)
        
        # Check display mode and render appropriate template
        if survey.display_mode == 'multi_page':
            # Flatten all questions into a single list with category info
            all_questions_flat = []
            for category in categories:
                for question in questions_by_category.get(category.id, []):
                    all_questions_flat.append({
                        'question': question,
                        'category': category,
                        'question_index': len(all_questions_flat)
                    })
            for question in questions_without_category:
                all_questions_flat.append({
                    'question': question,
                    'category': None,
                    'question_index': len(all_questions_flat)
                })
            
            return render_template('survey/public/questions_multi_page.html',
                                 survey=survey,
                                 all_questions=all_questions_flat,
                                 total_questions=len(all_questions_flat),
                                 user_display_name=display_name)
        else:
            # Single page mode (existing template)
            return render_template('survey/public/questions.html',
                                 survey=survey,
                                 categories=categories,
                                 questions_by_category=questions_by_category,
                                 questions_without_category=questions_without_category,
                                 user_display_name=display_name)
        
    except Exception as e:
        logger.error(f"Error in survey_questions: {e}", exc_info=True)
        return render_template('error.html', error=f"خطا در بارگذاری سوالات: {str(e)}"), 500


def handle_survey_submission(survey_id, survey, user, national_id, is_anonymous_access=False):
    """Handle survey response submission"""
    try:
        # For anonymous access, we need to track by IP address or session
        # Since we can't use user_id or national_id, we'll use IP address
        identifier_field = 'user_id' if user else 'national_id'
        identifier_value = user.id if user else (national_id if national_id else None)
        
        # For anonymous access without user or national_id, use IP address as identifier
        if is_anonymous_access and not user and not national_id:
            # Use IP address as a fallback identifier
            ip_address = request.remote_addr
            # Query by IP and survey_id for anonymous responses
            response = SurveyResponse.query.filter_by(
                survey_id=survey_id,
                user_id=None,
                national_id=None,
                ip_address=ip_address,
                is_completed=False
            ).order_by(desc(SurveyResponse.started_at)).first()
        else:
            # Normal query for authenticated users
            response = SurveyResponse.query.filter_by(
                survey_id=survey_id,
                user_id=user.id if user else None,
                national_id=national_id if not user else None,
                is_completed=False
            ).order_by(desc(SurveyResponse.started_at)).first()
        
        if not response:
            # Create new response
            period_key = get_completion_period_key(survey.completion_period_type)
            response = SurveyResponse(
                survey_id=survey_id,
                user_id=user.id if user else None,
                national_id=national_id if not user and not is_anonymous_access else None,
                started_at=datetime.utcnow(),
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent'),
                completion_period_key=period_key,
                is_completed=False
            )
            db.session.add(response)
            db.session.flush()
        
        # Get all questions
        questions = SurveyQuestion.query.filter_by(survey_id=survey_id).all()
        
        # Save answers
        for question in questions:
            answer_key = f"question_{question.id}"
            
            # Check if answer exists
            existing_answer = SurveyAnswerItem.query.filter_by(
                response_id=response.id,
                question_id=question.id
            ).first()
            
            if existing_answer:
                answer_item = existing_answer
            else:
                answer_item = SurveyAnswerItem(
                    response_id=response.id,
                    question_id=question.id
                )
                db.session.add(answer_item)
            
            # Handle different question types
            if question.question_type.startswith('likert_'):
                answer_value = request.form.get(answer_key)
                if answer_value:
                    try:
                        answer_item.answer_value = int(answer_value)
                    except:
                        pass
            elif question.question_type == 'text':
                answer_text = request.form.get(answer_key, '').strip()
                if answer_text:
                    # Validate character count
                    max_chars = question.max_words or 100  # max_words field stores max characters
                    char_count = len(answer_text)
                    if char_count > max_chars:
                        flash(f'تعداد حروف پاسخ سوال "{question.question_text[:50]}..." نباید بیشتر از {max_chars} باشد. تعداد فعلی: {char_count}', 'error')
                        return redirect(url_for('survey.survey_questions', survey_id=survey_id))
                    
                    # Apply validation if question has validation_type and is single_line
                    if question.text_input_type == 'single_line' and question.validation_type:
                        is_valid, error_msg = validate_answer_by_type(answer_text, question.validation_type)
                        if not is_valid:
                            flash(f'خطا در پاسخ سوال "{question.question_text[:50]}...": {error_msg}', 'error')
                            return redirect(url_for('survey.survey_questions', survey_id=survey_id))
                    
                    answer_item.answer_text = sanitize_input(answer_text)
            elif question.question_type == 'file_upload':
                # Handle file upload (if needed)
                if answer_key in request.files:
                    file = request.files[answer_key]
                    if file and file.filename:
                        # Validate file size
                        max_size_mb = question.max_file_size_mb or 25
                        max_size_bytes = max_size_mb * 1024 * 1024
                        
                        # Check file size
                        file.seek(0, 2)  # Seek to end
                        file_size = file.tell()
                        file.seek(0)  # Reset to beginning
                        
                        if file_size > max_size_bytes:
                            flash(f'حجم فایل برای سوال "{question.question_text[:50]}..." نباید بیشتر از {max_size_mb} مگابایت باشد', 'error')
                            return redirect(url_for('survey.survey_questions', survey_id=survey_id))
                        
                        from .utils import validate_file_upload
                        is_valid, error_msg = validate_file_upload(file, max_size_mb=question.max_file_size_mb)
                        if is_valid:
                            import os
                            # Get the app directory (where app.py is located)
                            BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))  # app/
                            upload_dir = os.path.join(BASE_DIR, 'static', 'uploads', 'surveys', 'files')
                            os.makedirs(upload_dir, exist_ok=True)
                            filename = f"response_{response.id}_q{question.id}_{file.filename}"
                            file_path = os.path.join(upload_dir, filename)
                            file.save(file_path)
                            answer_item.file_path = f"/static/uploads/surveys/files/{filename}"
        
        # Save survey parameters (for anonymous surveys)
        if is_anonymous_access and survey.access_type == 'anonymous':
            # Get parameters from session
            parameters_dict = session.get(f'anonymous_survey_{survey_id}_parameters', {})
            
            if parameters_dict:
                # Get all survey parameters
                survey_parameters = SurveyParameter.query.filter_by(survey_id=survey_id).all()
                param_name_to_id = {p.parameter_name: p.id for p in survey_parameters}
                
                # Save each parameter value
                for param_name, param_value in parameters_dict.items():
                    if param_name in param_name_to_id:
                        param_id = param_name_to_id[param_name]
                        
                        # Check if parameter response already exists
                        existing_param_response = SurveyResponseParameter.query.filter_by(
                            response_id=response.id,
                            parameter_id=param_id
                        ).first()
                        
                        if existing_param_response:
                            existing_param_response.parameter_value = param_value
                        else:
                            param_response = SurveyResponseParameter(
                                response_id=response.id,
                                parameter_id=param_id,
                                parameter_value=param_value
                            )
                            db.session.add(param_response)
        
        # Mark as completed
        response.is_completed = True
        response.completed_at = datetime.utcnow()
        
        db.session.commit()
        
        log_survey_action('submit_survey_response', 'survey', survey_id, {
            'response_id': response.id
        })
        
        display_name = get_user_display_name_from_session()
        
        # For anonymous surveys, include hash in redirect URL
        hash_param = None
        if is_anonymous_access:
            hash_in_session = session.get(f'anonymous_survey_{survey_id}')
            hash_param = request.args.get('hash') or hash_in_session
        
        if hash_param:
            return redirect(url_for('survey.survey_complete', survey_id=survey_id, hash=hash_param))
        else:
            return redirect(url_for('survey.survey_complete', survey_id=survey_id))
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error submitting survey: {e}", exc_info=True)
        flash('خطا در ثبت پاسخ‌ها. لطفاً دوباره تلاش کنید', 'error')
        return redirect(url_for('survey.survey_questions', survey_id=survey_id))


@survey_bp.route('/<int:survey_id>/complete')
@requires_auth_or_anonymous
def survey_complete(survey_id):
    """Thank you page after completing survey"""
    try:
        survey = Survey.query.get_or_404(survey_id)
        
        # Check if this is anonymous access
        is_anonymous_access = False
        if survey.access_type == 'anonymous':
            hash_param = request.args.get('hash')
            hash_in_session = session.get(f'anonymous_survey_{survey_id}')
            
            if hash_param and verify_anonymous_access_hash(survey_id, hash_param):
                is_anonymous_access = True
            elif hash_in_session and verify_anonymous_access_hash(survey_id, hash_in_session):
                is_anonymous_access = True
        
        display_name = get_user_display_name_from_session() if not is_anonymous_access else "کاربر گرامی"
        
        log_survey_action('view_survey_complete', 'survey', survey_id)
        return render_template('survey/public/complete.html',
                             survey=survey,
                             user_display_name=display_name)
    except Exception as e:
        logger.error(f"Error in survey_complete: {e}", exc_info=True)
        return render_template('error.html', error=f"خطا: {str(e)}"), 500

