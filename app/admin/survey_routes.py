"""
Admin Panel Survey Routes
Routes for managing survey managers and viewing all surveys
"""
from flask import render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import current_user
from . import admin_bp
from .utils import admin_required, log_action
from models import User
from survey_models import SurveyManager, Survey, SurveyResponse, SurveyQuestion, SurveyCategory, SurveyAnswerItem
from extensions import db
from sqlalchemy import or_, func, desc
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# Note: Survey managers are now managed through User Types
# Use /admin/user-types to manage "مسئول نظرسنجی" user type
# The survey_managers_list, create, toggle, and delete routes have been removed
# Users with "مسئول نظرسنجی" user type are automatically recognized as survey managers

@admin_bp.route('/survey/surveys')
@admin_required
def survey_surveys_list():
    """List all surveys (admin view)"""
    try:
        surveys = db.session.query(Survey, SurveyManager, User).join(
            SurveyManager, Survey.manager_id == SurveyManager.id
        ).join(
            User, SurveyManager.user_id == User.id
        ).order_by(desc(Survey.created_at)).all()
        
        surveys_data = []
        for survey, manager, user in surveys:
            # Count responses
            total_responses = SurveyResponse.query.filter_by(survey_id=survey.id).count()
            completed_responses = SurveyResponse.query.filter_by(
                survey_id=survey.id,
                is_completed=True
            ).count()
            
            surveys_data.append({
                'survey': survey,
                'manager': manager,
                'manager_user': user,
                'total_responses': total_responses,
                'completed_responses': completed_responses
            })
        
        log_action('view_all_surveys', 'survey', None)
        return render_template('admin/survey/surveys/list.html', surveys=surveys_data)
    except Exception as e:
        logger.error(f"Error listing surveys: {e}", exc_info=True)
        flash('خطا در نمایش لیست پرسشنامه‌ها', 'error')
        return redirect(url_for('admin.index'))


@admin_bp.route('/survey/surveys/<int:survey_id>/view')
@admin_required
def survey_surveys_view(survey_id):
    """View survey details (admin)"""
    try:
        survey = Survey.query.get_or_404(survey_id)
        manager = SurveyManager.query.get(survey.manager_id)
        manager_user = User.query.get(manager.user_id) if manager else None
        
        # Get statistics
        total_responses = SurveyResponse.query.filter_by(survey_id=survey_id).count()
        completed_responses = SurveyResponse.query.filter_by(
            survey_id=survey_id,
            is_completed=True
        ).count()
        attempted_responses = SurveyResponse.query.filter_by(
            survey_id=survey_id,
            is_completed=False
        ).count()
        
        log_action('view_survey', 'survey', survey_id)
        return render_template('admin/survey/surveys/view.html', 
                             survey=survey,
                             manager=manager,
                             manager_user=manager_user,
                             total_responses=total_responses,
                             completed_responses=completed_responses,
                             attempted_responses=attempted_responses)
    except Exception as e:
        logger.error(f"Error viewing survey: {e}", exc_info=True)
        flash('خطا در نمایش پرسشنامه', 'error')
        return redirect(url_for('admin.survey_surveys_list'))


@admin_bp.route('/survey/surveys/<int:survey_id>/edit', methods=['GET', 'POST'])
@admin_required
def survey_surveys_edit(survey_id):
    """Edit survey (admin) - uses manager edit template"""
    try:
        survey = Survey.query.get_or_404(survey_id)
        
        if request.method == 'POST':
            try:
                from survey.utils import sanitize_input
                survey.title = sanitize_input(request.form.get('title', '').strip())
                survey.description = sanitize_input(request.form.get('description', '').strip())
                survey.status = request.form.get('status', 'active')
                survey.access_type = request.form.get('access_type', 'public')
                survey.max_completions_per_user = int(request.form.get('max_completions_per_user', 1))
                survey.completion_period_type = request.form.get('completion_period_type', 'yearly')
                survey.welcome_message = sanitize_input(request.form.get('welcome_message', '').strip())
                survey.welcome_button_text = sanitize_input(request.form.get('welcome_button_text', 'شروع نظرسنجی').strip())
                survey.display_mode = request.form.get('display_mode', 'multi_page')
                
                # Date parsing (Jalali to Gregorian)
                from jdatetime import datetime as jdatetime
                if request.form.get('start_date'):
                    try:
                        # Parse Jalali date (format: YYYY/MM/DD)
                        jalali_str = request.form.get('start_date').strip()
                        if jalali_str:
                            jalali_parts = list(map(int, jalali_str.split('/')))
                            jalali_dt = jdatetime.datetime(jalali_parts[0], jalali_parts[1], jalali_parts[2])
                            survey.start_date = jalali_dt.togregorian()
                        else:
                            survey.start_date = None
                    except Exception as e:
                        logger.warning(f"Error parsing start_date: {e}")
                        pass
                else:
                    survey.start_date = None
                
                if request.form.get('end_date'):
                    try:
                        # Parse Jalali date (format: YYYY/MM/DD)
                        jalali_str = request.form.get('end_date').strip()
                        if jalali_str:
                            jalali_parts = list(map(int, jalali_str.split('/')))
                            jalali_dt = jdatetime.datetime(jalali_parts[0], jalali_parts[1], jalali_parts[2])
                            survey.end_date = jalali_dt.togregorian()
                        else:
                            survey.end_date = None
                    except Exception as e:
                        logger.warning(f"Error parsing end_date: {e}")
                        pass
                else:
                    survey.end_date = None
                
                # Handle logo deletion
                import os
                delete_logo = request.form.get('delete_logo', '0')
                if delete_logo == '1':
                    # Delete existing logo
                    if survey.logo_path:
                        old_path = os.path.join('app', 'static', survey.logo_path.lstrip('/'))
                        if os.path.exists(old_path):
                            try:
                                os.remove(old_path)
                            except Exception as e:
                                logger.warning(f"Error deleting old logo: {e}")
                        survey.logo_path = None
                
                # Handle logo upload
                # فقط اگر فایل واقعاً ارسال شده باشد (filename خالی نباشد)
                logo_file = request.files.get('logo')
                if logo_file:
                    # بررسی دقیق‌تر: filename باید وجود داشته باشد و خالی نباشد
                    filename = getattr(logo_file, 'filename', None) or ''
                    filename = filename.strip() if filename else ''
                    
                    # فقط اگر filename واقعاً وجود داشته باشد، فایل را پردازش کن
                    if filename:
                        from survey.utils import validate_logo_upload
                        is_valid, error_msg = validate_logo_upload(logo_file, max_size_mb=2)
                        if is_valid:
                            # Delete old logo if exists
                            if survey.logo_path:
                                old_path = os.path.join('app', 'static', survey.logo_path.lstrip('/'))
                                if os.path.exists(old_path):
                                    try:
                                        os.remove(old_path)
                                    except Exception as e:
                                        logger.warning(f"Error deleting old logo: {e}")
                            
                            # Save new logo
                            upload_dir = os.path.join('app', 'static', 'uploads', 'surveys', 'logos')
                            os.makedirs(upload_dir, exist_ok=True)
                            from werkzeug.utils import secure_filename
                            safe_filename = secure_filename(logo_file.filename)
                            logo_filename = f"survey_{survey.id}_{safe_filename}"
                            logo_path = os.path.join(upload_dir, logo_filename)
                            logo_file.save(logo_path)
                            survey.logo_path = f"/static/uploads/surveys/logos/{logo_filename}"
                        else:
                            flash(f'خطا در آپلود لوگو: {error_msg}', 'error')
                            logger.warning(f"Logo upload validation failed: {error_msg}")
                    # اگر filename خالی است، هیچ کاری نکنید (نه خطا بدهید)
                
                db.session.commit()
                
                log_action('edit_survey', 'survey', survey_id, {'admin_edit': True})
                flash('پرسشنامه با موفقیت به‌روزرسانی شد', 'success')
                return redirect(url_for('admin.survey_surveys_list'))
                
            except Exception as e:
                db.session.rollback()
                logger.error(f"Error editing survey: {e}", exc_info=True)
                flash('خطا در به‌روزرسانی پرسشنامه', 'error')
        
        # GET request - show edit form
        return render_template('survey/manager/surveys/edit.html', 
                             survey=survey,
                             is_admin=True)
    except Exception as e:
        logger.error(f"Error in survey edit: {e}", exc_info=True)
        flash('خطا در نمایش فرم ویرایش', 'error')
        return redirect(url_for('admin.survey_surveys_list'))


@admin_bp.route('/survey/surveys/<int:survey_id>/questions')
@admin_required
def survey_surveys_questions(survey_id):
    """Manage survey questions (admin) - uses manager questions template"""
    try:
        survey = Survey.query.get_or_404(survey_id)
        
        # Get categories and questions
        from survey_models import SurveyCategory, SurveyQuestion
        categories = SurveyCategory.query.filter_by(survey_id=survey_id).order_by(SurveyCategory.order).all()
        questions = SurveyQuestion.query.filter_by(survey_id=survey_id).order_by(SurveyQuestion.order).all()
        
        # Get last question for auto-fill (if exists)
        last_question = None
        if questions:
            last_question = SurveyQuestion.query.filter_by(survey_id=survey_id).order_by(
                desc(SurveyQuestion.id)
            ).first()
        
        log_action('view_survey_questions', 'survey', survey_id, {'admin_view': True})
        return render_template('survey/manager/surveys/questions.html',
                             survey=survey,
                             categories=categories,
                             questions=questions,
                             last_question=last_question,
                             is_admin=True)
    except Exception as e:
        logger.error(f"Error viewing survey questions: {e}", exc_info=True)
        flash('خطا در نمایش سوالات', 'error')
        return redirect(url_for('admin.survey_surveys_list'))


@admin_bp.route('/survey/surveys/<int:survey_id>/questions/create', methods=['POST'])
@admin_required
def survey_questions_create(survey_id):
    """Create a new question (AJAX) - admin"""
    try:
        survey = Survey.query.get_or_404(survey_id)
        
        from survey.utils import sanitize_input
        data = request.get_json()
        question_type = data.get('question_type')
        question_text = sanitize_input(data.get('question_text', '').strip())
        category_id = data.get('category_id')
        order = data.get('order', 0)
        is_required = data.get('is_required', True)
        options = data.get('options')  # For Likert scale questions
        option_display_type = data.get('option_display_type', 'radio')  # Default to radio
        text_input_type = data.get('text_input_type', 'multi_line')  # Default to multi_line
        validation_type = data.get('validation_type')  # Can be None, 'national_id', 'email', 'landline', 'mobile', 'website'
        
        if not question_text:
            return jsonify({'success': False, 'message': 'متن سوال الزامی است'}), 400
        
        from survey_models import SurveyQuestion
        # Get max_words and max_file_size_mb based on question type
        max_words = None
        max_file_size_mb = None
        if question_type == 'text':
            max_words = data.get('max_words', 100)  # Default: 100 characters (stored in max_words field)
            if max_words and (max_words < 1 or max_words > 2000):
                return jsonify({'success': False, 'message': 'حداکثر تعداد حروف باید بین 1 تا 2000 باشد'}), 400
        elif question_type == 'file_upload':
            max_file_size_mb = data.get('max_file_size_mb', 25)  # Default: 25 MB
            if max_file_size_mb and (max_file_size_mb < 1 or max_file_size_mb > 50):
                return jsonify({'success': False, 'message': 'حداکثر حجم فایل باید بین 1 تا 50 مگابایت باشد'}), 400
        # For Likert questions, both will remain None
        
        question = SurveyQuestion(
            survey_id=survey_id,
            category_id=category_id if category_id else None,
            question_type=question_type,
            question_text=question_text,
            description=sanitize_input(data.get('description', '').strip()),
            order=order,
            is_required=is_required,
            options=options,
            option_display_type=option_display_type,
            text_input_type=text_input_type,
            validation_type=validation_type,
            max_words=max_words,
            max_file_size_mb=max_file_size_mb
        )
        
        db.session.add(question)
        db.session.commit()
        
        log_action('create_question', 'question', question.id, {'survey_id': survey_id, 'admin_edit': True})
        return jsonify({'success': True, 'message': 'سوال با موفقیت ایجاد شد', 'question_id': question.id})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating question: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'خطا در ایجاد سوال'}), 500


@admin_bp.route('/survey/surveys/<int:survey_id>/categories/create', methods=['POST'])
@admin_required
def survey_categories_create(survey_id):
    """Create a new category (AJAX) - admin"""
    try:
        survey = Survey.query.get_or_404(survey_id)
        
        from survey.utils import sanitize_input
        data = request.get_json()
        title = sanitize_input(data.get('title', '').strip())
        description = sanitize_input(data.get('description', '').strip())
        order = data.get('order', 0)
        
        if not title:
            return jsonify({'success': False, 'message': 'عنوان دسته‌بندی الزامی است'}), 400
        
        from survey_models import SurveyCategory
        category = SurveyCategory(
            survey_id=survey_id,
            title=title,
            description=description,
            order=order
        )
        
        db.session.add(category)
        db.session.commit()
        
        log_action('create_category', 'category', category.id, {'survey_id': survey_id, 'admin_edit': True})
        return jsonify({'success': True, 'message': 'دسته‌بندی با موفقیت ایجاد شد', 'category_id': category.id})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating category: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'خطا در ایجاد دسته‌بندی'}), 500


@admin_bp.route('/survey/questions/<int:question_id>/edit', methods=['POST'])
@admin_required
def survey_questions_edit(question_id):
    """Edit a question (AJAX) - admin"""
    try:
        from survey.utils import sanitize_input
        from survey_models import SurveyQuestion
        
        question = SurveyQuestion.query.get_or_404(question_id)
        
        data = request.get_json()
        question.question_type = data.get('question_type')
        question.question_text = sanitize_input(data.get('question_text', '').strip())
        question.description = sanitize_input(data.get('description', '').strip())
        question.category_id = data.get('category_id') if data.get('category_id') else None
        question.is_required = data.get('is_required', True)
        question.options = data.get('options')  # For Likert scale questions
        question.option_display_type = data.get('option_display_type', 'radio')  # Default to radio
        question.text_input_type = data.get('text_input_type', 'multi_line')  # Default to multi_line
        question.validation_type = data.get('validation_type')  # Can be None, 'national_id', 'email', 'landline', 'mobile', 'website'
        
        # Update max_words and max_file_size_mb based on question type
        if question.question_type == 'text':
            max_words = data.get('max_words', 100)  # Default: 100 characters (stored in max_words field)
            if max_words and (max_words < 1 or max_words > 2000):
                return jsonify({'success': False, 'message': 'حداکثر تعداد حروف باید بین 1 تا 2000 باشد'}), 400
            question.max_words = max_words
            question.max_file_size_mb = None  # Clear file size limit for text questions
        elif question.question_type == 'file_upload':
            max_file_size_mb = data.get('max_file_size_mb', 25)  # Default: 25 MB
            if max_file_size_mb and (max_file_size_mb < 1 or max_file_size_mb > 50):
                return jsonify({'success': False, 'message': 'حداکثر حجم فایل باید بین 1 تا 50 مگابایت باشد'}), 400
            question.max_file_size_mb = max_file_size_mb
            question.max_words = None  # Clear word limit for file questions
        else:
            # For Likert questions, clear both limits
            question.max_words = None
            question.max_file_size_mb = None
        
        if not question.question_text:
            return jsonify({'success': False, 'message': 'متن سوال الزامی است'}), 400
        
        db.session.commit()
        
        log_action('edit_question', 'question', question_id, {'survey_id': question.survey_id, 'admin_edit': True})
        return jsonify({'success': True, 'message': 'سوال با موفقیت به‌روزرسانی شد'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error editing question: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'خطا در به‌روزرسانی سوال'}), 500


@admin_bp.route('/survey/surveys/<int:survey_id>/questions/reorder', methods=['POST'])
@admin_required
def survey_questions_reorder(survey_id):
    """Reorder questions (AJAX) - admin"""
    try:
        survey = Survey.query.get_or_404(survey_id)
        
        from survey_models import SurveyQuestion
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
        
        log_action('reorder_questions', 'survey', survey_id, {'admin_edit': True})
        return jsonify({'success': True, 'message': 'ترتیب سوالات با موفقیت به‌روزرسانی شد'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error reordering questions: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'خطا در به‌روزرسانی ترتیب'}), 500


@admin_bp.route('/survey/surveys/<int:survey_id>/responses')
@admin_required
def survey_surveys_responses(survey_id):
    """View survey responses (admin)"""
    try:
        survey = Survey.query.get_or_404(survey_id)
        responses = SurveyResponse.query.filter_by(survey_id=survey_id).order_by(
            desc(SurveyResponse.completed_at),
            desc(SurveyResponse.started_at)
        ).all()
        
        log_action('view_survey_responses', 'survey', survey_id)
        return render_template('admin/survey/surveys/responses.html',
                             survey=survey,
                             responses=responses)
    except Exception as e:
        logger.error(f"Error viewing survey responses: {e}", exc_info=True)
        flash('خطا در نمایش پاسخ‌ها', 'error')
        return redirect(url_for('admin.survey_surveys_list'))

