"""
Public Survey Routes
Routes for users to complete surveys
"""
from flask import render_template, request, jsonify, redirect, url_for, flash, session, make_response
from flask_login import current_user
from auth_utils import requires_auth
from . import survey_bp
from .utils import (
    log_survey_action, check_survey_access, check_completion_limit, 
    sanitize_input, get_completion_period_key
)
from models import User
from survey_models import (
    Survey, SurveyResponse, SurveyAnswerItem, SurveyQuestion, 
    SurveyCategory, SurveyAllowedUser, SurveyManager
)
from extensions import db
from datetime import datetime
from sqlalchemy import desc
import logging
import json

logger = logging.getLogger(__name__)

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


@survey_bp.route('/<int:survey_id>/start')
@requires_auth
def survey_start(survey_id):
    """Start survey - welcome page with access check"""
    try:
        survey = Survey.query.get_or_404(survey_id)
        
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
        
        # Get user info
        user_info = session.get("user_info")
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
        
        # Check access (skip for manager owners)
        if not is_manager_owner:
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
        
        # Check completion limit (skip for manager owners - they can test their surveys)
        if not is_manager_owner:
            can_complete, limit_msg, current_count = check_completion_limit(user, survey, national_id)
            if not can_complete:
                flash(limit_msg, 'error')
                return redirect(url_for('survey'))
        
        display_name = get_user_display_name_from_session()
        
        log_survey_action('view_survey_welcome', 'survey', survey_id)
        return render_template('survey/public/welcome.html', 
                             survey=survey,
                             user_display_name=display_name)
    except Exception as e:
        logger.error(f"Error in survey_start: {e}", exc_info=True)
        return render_template('error.html', error=f"خطا در بارگذاری نظرسنجی: {str(e)}"), 500


@survey_bp.route('/<int:survey_id>/questions', methods=['GET', 'POST'])
@requires_auth
def survey_questions(survey_id):
    """Display survey questions and handle submission"""
    try:
        survey = Survey.query.get_or_404(survey_id)
        
        # Check if survey is active
        if survey.status != 'active':
            flash('این پرسشنامه در حال حاضر فعال نیست', 'error')
            return redirect(url_for('survey'))
        
        # Get user info
        user_info = session.get("user_info")
        username = user_info.get('username', '').lower() if user_info else None
        user = User.query.filter_by(sso_id=username).first() if username else None
        national_id = user_info.get('national_id') if user_info else None
        
        if request.method == 'POST':
            # Handle form submission
            return handle_survey_submission(survey_id, survey, user, national_id)
        
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
        
        display_name = get_user_display_name_from_session()
        
        log_survey_action('view_survey_questions', 'survey', survey_id)
        return render_template('survey/public/questions.html',
                             survey=survey,
                             categories=categories,
                             questions_by_category=questions_by_category,
                             questions_without_category=questions_without_category,
                             user_display_name=display_name)
        
    except Exception as e:
        logger.error(f"Error in survey_questions: {e}", exc_info=True)
        return render_template('error.html', error=f"خطا در بارگذاری سوالات: {str(e)}"), 500


def handle_survey_submission(survey_id, survey, user, national_id):
    """Handle survey response submission"""
    try:
        # Create or get response record
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
                national_id=national_id if not user else None,
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
                    answer_item.answer_text = sanitize_input(answer_text)
            elif question.question_type == 'file_upload':
                # Handle file upload (if needed)
                if answer_key in request.files:
                    file = request.files[answer_key]
                    if file and file.filename:
                        from .utils import validate_file_upload
                        is_valid, error_msg = validate_file_upload(file)
                        if is_valid:
                            import os
                            upload_dir = os.path.join('app', 'static', 'uploads', 'surveys', 'files')
                            os.makedirs(upload_dir, exist_ok=True)
                            filename = f"response_{response.id}_q{question.id}_{file.filename}"
                            file_path = os.path.join(upload_dir, filename)
                            file.save(file_path)
                            answer_item.file_path = f"/static/uploads/surveys/files/{filename}"
        
        # Mark as completed
        response.is_completed = True
        response.completed_at = datetime.utcnow()
        
        db.session.commit()
        
        log_survey_action('submit_survey_response', 'survey', survey_id, {
            'response_id': response.id
        })
        
        display_name = get_user_display_name_from_session()
        return redirect(url_for('survey.survey_complete', survey_id=survey_id))
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error submitting survey: {e}", exc_info=True)
        flash('خطا در ثبت پاسخ‌ها. لطفاً دوباره تلاش کنید', 'error')
        return redirect(url_for('survey.survey_questions', survey_id=survey_id))


@survey_bp.route('/<int:survey_id>/complete')
@requires_auth
def survey_complete(survey_id):
    """Thank you page after completing survey"""
    try:
        survey = Survey.query.get_or_404(survey_id)
        display_name = get_user_display_name_from_session()
        
        log_survey_action('view_survey_complete', 'survey', survey_id)
        return render_template('survey/public/complete.html',
                             survey=survey,
                             user_display_name=display_name)
    except Exception as e:
        logger.error(f"Error in survey_complete: {e}", exc_info=True)
        return render_template('error.html', error=f"خطا: {str(e)}"), 500

