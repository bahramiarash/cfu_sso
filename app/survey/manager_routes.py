"""
Survey Manager Routes
Routes for survey managers to create and manage surveys
"""
from flask import render_template, request, jsonify, redirect, url_for, flash, session, send_file
from flask_login import current_user, login_required
from . import survey_bp
from .utils import log_survey_action, sanitize_input, is_survey_manager
from models import User
from survey_models import (
    SurveyManager, Survey, SurveyCategory, SurveyQuestion,
    SurveyAccessGroup, SurveyAllowedUser, SurveyResponse, SurveyAnswerItem
)
from extensions import db
from sqlalchemy import desc, func
from datetime import datetime
from jdatetime import datetime as jdatetime
import logging
import json
import os

logger = logging.getLogger(__name__)


def manager_required(f):
    """Decorator to require survey manager access"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            from flask import abort
            abort(401)
        if not is_survey_manager(current_user):
            from flask import abort
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


@survey_bp.route('/manager/dashboard')
@login_required
@manager_required
def manager_dashboard():
    """Survey manager dashboard"""
    try:
        manager = SurveyManager.query.filter_by(user_id=current_user.id, is_active=True).first()
        if not manager:
            flash('شما به عنوان مسئول نظرسنجی تعریف نشده‌اید', 'error')
            return redirect(url_for('list_tools'))
        
        # Get manager's surveys
        surveys = Survey.query.filter_by(manager_id=manager.id).order_by(desc(Survey.created_at)).all()
        
        # Get statistics
        stats = {
            'total_surveys': len(surveys),
            'active_surveys': len([s for s in surveys if s.status == 'active']),
            'total_responses': 0,
            'completed_responses': 0
        }
        
        for survey in surveys:
            total = SurveyResponse.query.filter_by(survey_id=survey.id).count()
            completed = SurveyResponse.query.filter_by(survey_id=survey.id, is_completed=True).count()
            stats['total_responses'] += total
            stats['completed_responses'] += completed
        
        log_survey_action('view_manager_dashboard', 'survey_manager', manager.id)
        return render_template('survey/manager/dashboard.html', 
                             manager=manager,
                             surveys=surveys,
                             stats=stats)
    except Exception as e:
        logger.error(f"Error in manager dashboard: {e}", exc_info=True)
        flash('خطا در نمایش داشبورد', 'error')
        return redirect(url_for('list_tools'))


@survey_bp.route('/manager/surveys')
@login_required
@manager_required
def manager_surveys_list():
    """List manager's surveys"""
    try:
        manager = SurveyManager.query.filter_by(user_id=current_user.id, is_active=True).first()
        if not manager:
            flash('شما به عنوان مسئول نظرسنجی تعریف نشده‌اید', 'error')
            return redirect(url_for('list_tools'))
        
        surveys = Survey.query.filter_by(manager_id=manager.id).order_by(desc(Survey.created_at)).all()
        
        surveys_data = []
        for survey in surveys:
            total = SurveyResponse.query.filter_by(survey_id=survey.id).count()
            completed = SurveyResponse.query.filter_by(survey_id=survey.id, is_completed=True).count()
            surveys_data.append({
                'survey': survey,
                'total_responses': total,
                'completed_responses': completed
            })
        
        log_survey_action('view_surveys_list', 'survey', None)
        return render_template('survey/manager/surveys/list.html', surveys=surveys_data)
    except Exception as e:
        logger.error(f"Error listing surveys: {e}", exc_info=True)
        flash('خطا در نمایش لیست پرسشنامه‌ها', 'error')
        return redirect(url_for('survey.manager_dashboard'))


@survey_bp.route('/manager/surveys/create', methods=['GET', 'POST'])
@login_required
@manager_required
def manager_surveys_create():
    """Create a new survey"""
    manager = SurveyManager.query.filter_by(user_id=current_user.id, is_active=True).first()
    if not manager:
        flash('شما به عنوان مسئول نظرسنجی تعریف نشده‌اید', 'error')
        return redirect(url_for('list_tools'))
    
    if request.method == 'POST':
        try:
            # Get form data
            title = sanitize_input(request.form.get('title', '').strip())
            description = sanitize_input(request.form.get('description', '').strip())
            
            if not title:
                flash('عنوان پرسشنامه الزامی است', 'error')
                return render_template('survey/manager/surveys/create.html')
            
            # Date parsing
            start_date = None
            end_date = None
            if request.form.get('start_date'):
                try:
                    start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
                except:
                    pass
            
            if request.form.get('end_date'):
                try:
                    end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d')
                except:
                    pass
            
            # Create survey
            survey = Survey(
                title=title,
                description=description,
                manager_id=manager.id,
                start_date=start_date,
                end_date=end_date,
                status=request.form.get('status', 'active'),
                access_type=request.form.get('access_type', 'public'),
                max_completions_per_user=int(request.form.get('max_completions_per_user', 1)),
                completion_period_type=request.form.get('completion_period_type', 'yearly'),
                welcome_message=sanitize_input(request.form.get('welcome_message', '').strip()),
                welcome_button_text=sanitize_input(request.form.get('welcome_button_text', 'شروع نظرسنجی').strip()),
                display_mode=request.form.get('display_mode', 'multi_page')
            )
            
            db.session.add(survey)
            db.session.flush()  # Get survey.id
            
            # Handle logo upload
            if 'logo' in request.files:
                logo_file = request.files['logo']
                if logo_file and logo_file.filename:
                    from .utils import validate_file_upload
                    is_valid, error_msg = validate_file_upload(logo_file)
                    if is_valid:
                        # Save logo
                        upload_dir = os.path.join('app', 'static', 'uploads', 'surveys', 'logos')
                        os.makedirs(upload_dir, exist_ok=True)
                        logo_filename = f"survey_{survey.id}_{logo_file.filename}"
                        logo_path = os.path.join(upload_dir, logo_filename)
                        logo_file.save(logo_path)
                        survey.logo_path = f"/static/uploads/surveys/logos/{logo_filename}"
            
            db.session.commit()
            
            log_survey_action('create_survey', 'survey', survey.id, {
                'title': title,
                'access_type': survey.access_type
            })
            flash('پرسشنامه با موفقیت ایجاد شد', 'success')
            return redirect(url_for('survey.manager_surveys_questions', survey_id=survey.id))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating survey: {e}", exc_info=True)
            flash('خطا در ایجاد پرسشنامه', 'error')
            return render_template('survey/manager/surveys/create.html')
    
    return render_template('survey/manager/surveys/create.html')


@survey_bp.route('/manager/surveys/<int:survey_id>/edit', methods=['GET', 'POST'])
@login_required
@manager_required
def manager_surveys_edit(survey_id):
    """Edit a survey"""
    manager = SurveyManager.query.filter_by(user_id=current_user.id, is_active=True).first()
    if not manager:
        flash('شما به عنوان مسئول نظرسنجی تعریف نشده‌اید', 'error')
        return redirect(url_for('list_tools'))
    
    survey = Survey.query.get_or_404(survey_id)
    
    # Check ownership
    if survey.manager_id != manager.id:
        flash('شما دسترسی به این پرسشنامه ندارید', 'error')
        return redirect(url_for('survey.manager_surveys_list'))
    
    if request.method == 'POST':
        try:
            survey.title = sanitize_input(request.form.get('title', '').strip())
            survey.description = sanitize_input(request.form.get('description', '').strip())
            survey.status = request.form.get('status', 'active')
            survey.access_type = request.form.get('access_type', 'public')
            survey.max_completions_per_user = int(request.form.get('max_completions_per_user', 1))
            survey.completion_period_type = request.form.get('completion_period_type', 'yearly')
            survey.welcome_message = sanitize_input(request.form.get('welcome_message', '').strip())
            survey.welcome_button_text = sanitize_input(request.form.get('welcome_button_text', 'شروع نظرسنجی').strip())
            survey.display_mode = request.form.get('display_mode', 'multi_page')
            
            # Date parsing
            if request.form.get('start_date'):
                try:
                    survey.start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
                except:
                    pass
            else:
                survey.start_date = None
            
            if request.form.get('end_date'):
                try:
                    survey.end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d')
                except:
                    pass
            else:
                survey.end_date = None
            
            # Handle logo upload
            if 'logo' in request.files:
                logo_file = request.files['logo']
                if logo_file and logo_file.filename:
                    from .utils import validate_file_upload
                    is_valid, error_msg = validate_file_upload(logo_file)
                    if is_valid:
                        # Delete old logo if exists
                        if survey.logo_path:
                            old_path = os.path.join('app', 'static', survey.logo_path.lstrip('/'))
                            if os.path.exists(old_path):
                                os.remove(old_path)
                        
                        # Save new logo
                        upload_dir = os.path.join('app', 'static', 'uploads', 'surveys', 'logos')
                        os.makedirs(upload_dir, exist_ok=True)
                        logo_filename = f"survey_{survey.id}_{logo_file.filename}"
                        logo_path = os.path.join(upload_dir, logo_filename)
                        logo_file.save(logo_path)
                        survey.logo_path = f"/static/uploads/surveys/logos/{logo_filename}"
            
            db.session.commit()
            
            log_survey_action('edit_survey', 'survey', survey_id)
            flash('پرسشنامه با موفقیت به‌روزرسانی شد', 'success')
            return redirect(url_for('survey.manager_surveys_list'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error editing survey: {e}", exc_info=True)
            flash('خطا در به‌روزرسانی پرسشنامه', 'error')
    
    return render_template('survey/manager/surveys/edit.html', survey=survey)


@survey_bp.route('/manager/surveys/<int:survey_id>/questions')
@login_required
@manager_required
def manager_surveys_questions(survey_id):
    """Manage survey questions"""
    manager = SurveyManager.query.filter_by(user_id=current_user.id, is_active=True).first()
    if not manager:
        flash('شما به عنوان مسئول نظرسنجی تعریف نشده‌اید', 'error')
        return redirect(url_for('list_tools'))
    
    survey = Survey.query.get_or_404(survey_id)
    
    # Check ownership
    if survey.manager_id != manager.id:
        flash('شما دسترسی به این پرسشنامه ندارید', 'error')
        return redirect(url_for('survey.manager_surveys_list'))
    
    # Get categories and questions
    categories = SurveyCategory.query.filter_by(survey_id=survey_id).order_by(SurveyCategory.order).all()
    questions = SurveyQuestion.query.filter_by(survey_id=survey_id).order_by(SurveyQuestion.order).all()
    
    # Get last question for auto-fill (if exists)
    last_question = None
    if questions:
        # Get the last question by order or by id (most recently created)
        last_question = SurveyQuestion.query.filter_by(survey_id=survey_id).order_by(
            desc(SurveyQuestion.id)
        ).first()
    
    log_survey_action('view_survey_questions', 'survey', survey_id)
    return render_template('survey/manager/surveys/questions.html',
                         survey=survey,
                         categories=categories,
                         questions=questions,
                         last_question=last_question)


@survey_bp.route('/manager/surveys/<int:survey_id>/questions/create', methods=['POST'])
@login_required
@manager_required
def manager_questions_create(survey_id):
    """Create a new question (AJAX)"""
    try:
        manager = SurveyManager.query.filter_by(user_id=current_user.id, is_active=True).first()
        if not manager:
            return jsonify({'success': False, 'message': 'دسترسی غیرمجاز'}), 403
        
        survey = Survey.query.get_or_404(survey_id)
        if survey.manager_id != manager.id:
            return jsonify({'success': False, 'message': 'دسترسی غیرمجاز'}), 403
        
        data = request.get_json()
        question_type = data.get('question_type')
        question_text = sanitize_input(data.get('question_text', '').strip())
        category_id = data.get('category_id')
        order = data.get('order', 0)
        is_required = data.get('is_required', True)
        options = data.get('options')  # For Likert scale questions
        
        if not question_text:
            return jsonify({'success': False, 'message': 'متن سوال الزامی است'}), 400
        
        question = SurveyQuestion(
            survey_id=survey_id,
            category_id=category_id if category_id else None,
            question_type=question_type,
            question_text=question_text,
            description=sanitize_input(data.get('description', '').strip()),
            order=order,
            is_required=is_required,
            options=options
        )
        
        db.session.add(question)
        db.session.commit()
        
        log_survey_action('create_question', 'question', question.id, {'survey_id': survey_id})
        return jsonify({'success': True, 'message': 'سوال با موفقیت ایجاد شد', 'question_id': question.id})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating question: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'خطا در ایجاد سوال'}), 500


@survey_bp.route('/manager/surveys/<int:survey_id>/categories/create', methods=['POST'])
@login_required
@manager_required
def manager_categories_create(survey_id):
    """Create a new category (AJAX)"""
    try:
        manager = SurveyManager.query.filter_by(user_id=current_user.id, is_active=True).first()
        if not manager:
            return jsonify({'success': False, 'message': 'دسترسی غیرمجاز'}), 403
        
        survey = Survey.query.get_or_404(survey_id)
        if survey.manager_id != manager.id:
            return jsonify({'success': False, 'message': 'دسترسی غیرمجاز'}), 403
        
        data = request.get_json()
        title = sanitize_input(data.get('title', '').strip())
        description = sanitize_input(data.get('description', '').strip())
        order = data.get('order', 0)
        
        if not title:
            return jsonify({'success': False, 'message': 'عنوان دسته‌بندی الزامی است'}), 400
        
        category = SurveyCategory(
            survey_id=survey_id,
            title=title,
            description=description,
            order=order
        )
        
        db.session.add(category)
        db.session.commit()
        
        log_survey_action('create_category', 'category', category.id, {'survey_id': survey_id})
        return jsonify({'success': True, 'message': 'دسته‌بندی با موفقیت ایجاد شد', 'category_id': category.id})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating category: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'خطا در ایجاد دسته‌بندی'}), 500


@survey_bp.route('/manager/questions/<int:question_id>/edit', methods=['POST'])
@login_required
@manager_required
def manager_questions_edit(question_id):
    """Edit a question (AJAX)"""
    try:
        manager = SurveyManager.query.filter_by(user_id=current_user.id, is_active=True).first()
        if not manager:
            return jsonify({'success': False, 'message': 'دسترسی غیرمجاز'}), 403
        
        question = SurveyQuestion.query.get_or_404(question_id)
        survey = Survey.query.get_or_404(question.survey_id)
        
        if survey.manager_id != manager.id:
            return jsonify({'success': False, 'message': 'دسترسی غیرمجاز'}), 403
        
        data = request.get_json()
        question.question_type = data.get('question_type')
        question.question_text = sanitize_input(data.get('question_text', '').strip())
        question.description = sanitize_input(data.get('description', '').strip())
        question.category_id = data.get('category_id') if data.get('category_id') else None
        question.is_required = data.get('is_required', True)
        question.options = data.get('options')  # For Likert scale questions
        
        if not question.question_text:
            return jsonify({'success': False, 'message': 'متن سوال الزامی است'}), 400
        
        db.session.commit()
        
        log_survey_action('edit_question', 'question', question_id, {'survey_id': survey.id})
        return jsonify({'success': True, 'message': 'سوال با موفقیت به‌روزرسانی شد'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error editing question: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'خطا در به‌روزرسانی سوال'}), 500


@survey_bp.route('/manager/surveys/<int:survey_id>/questions/reorder', methods=['POST'])
@login_required
@manager_required
def manager_questions_reorder(survey_id):
    """Reorder questions (AJAX) - for drag & drop"""
    try:
        manager = SurveyManager.query.filter_by(user_id=current_user.id, is_active=True).first()
        if not manager:
            return jsonify({'success': False, 'message': 'دسترسی غیرمجاز'}), 403
        
        survey = Survey.query.get_or_404(survey_id)
        if survey.manager_id != manager.id:
            return jsonify({'success': False, 'message': 'دسترسی غیرمجاز'}), 403
        
        data = request.get_json()
        # Expected format: [{'question_id': 1, 'order': 0, 'category_id': 1}, ...]
        question_orders = data.get('questions', [])
        
        for item in question_orders:
            question_id = item.get('question_id')
            new_order = item.get('order', 0)
            new_category_id = item.get('category_id')
            
            question = SurveyQuestion.query.filter_by(id=question_id, survey_id=survey_id).first()
            if question:
                question.order = new_order
                if new_category_id is not None:
                    question.category_id = new_category_id if new_category_id else None
        
        db.session.commit()
        
        log_survey_action('reorder_questions', 'survey', survey_id)
        return jsonify({'success': True, 'message': 'ترتیب سوالات با موفقیت به‌روزرسانی شد'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error reordering questions: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'خطا در به‌روزرسانی ترتیب'}), 500


@survey_bp.route('/manager/surveys/<int:survey_id>/reports/overview')
@login_required
@manager_required
def manager_reports_overview(survey_id):
    """Survey reports overview"""
    try:
        manager = SurveyManager.query.filter_by(user_id=current_user.id, is_active=True).first()
        if not manager:
            flash('شما به عنوان مسئول نظرسنجی تعریف نشده‌اید', 'error')
            return redirect(url_for('list_tools'))
        
        survey = Survey.query.get_or_404(survey_id)
        if survey.manager_id != manager.id:
            flash('شما دسترسی به این پرسشنامه ندارید', 'error')
            return redirect(url_for('survey.manager_surveys_list'))
        
        # Get date range from query params (Jalali dates)
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        # Get all responses
        query = SurveyResponse.query.filter_by(survey_id=survey_id)
        
        # Filter by date range if provided
        if date_from:
            try:
                # Parse Jalali date
                jdate_from = jdatetime.strptime(date_from, '%Y/%m/%d')
                date_from_greg = jdate_from.togregorian()
                query = query.filter(SurveyResponse.started_at >= date_from_greg)
            except:
                pass
        
        if date_to:
            try:
                jdate_to = jdatetime.strptime(date_to, '%Y/%m/%d')
                date_to_greg = jdate_to.togregorian()
                # Add one day to include the entire end date
                date_to_greg = datetime.combine(date_to_greg.date(), datetime.max.time())
                query = query.filter(SurveyResponse.started_at <= date_to_greg)
            except:
                pass
        
        total_responses = query.count()
        completed_responses = query.filter_by(is_completed=True).count()
        attempted_responses = query.filter_by(is_completed=False).count()
        
        log_survey_action('view_survey_reports', 'survey', survey_id)
        return render_template('survey/manager/reports/overview.html',
                             survey=survey,
                             total_responses=total_responses,
                             completed_responses=completed_responses,
                             attempted_responses=attempted_responses,
                             date_from=date_from,
                             date_to=date_to)
    except Exception as e:
        logger.error(f"Error viewing reports: {e}", exc_info=True)
        flash('خطا در نمایش گزارش‌ها', 'error')
        return redirect(url_for('survey.manager_surveys_list'))

