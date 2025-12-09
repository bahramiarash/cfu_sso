"""
Admin Panel Survey Routes
Routes for managing survey managers and viewing all surveys
"""
from flask import render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import current_user
from . import admin_bp
from .utils import admin_required, log_action
from models import User
from survey_models import SurveyManager, Survey, SurveyResponse
from extensions import db
from sqlalchemy import or_, func, desc
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@admin_bp.route('/survey/managers')
@admin_required
def survey_managers_list():
    """List all survey managers"""
    try:
        managers = db.session.query(SurveyManager, User).join(
            User, SurveyManager.user_id == User.id
        ).order_by(desc(SurveyManager.created_at)).all()
        
        managers_data = []
        for manager, user in managers:
            # Count surveys for this manager
            survey_count = Survey.query.filter_by(manager_id=manager.id).count()
            managers_data.append({
                'manager': manager,
                'user': user,
                'survey_count': survey_count
            })
        
        log_action('view_survey_managers', 'survey_manager', None)
        return render_template('admin/survey/managers/list.html', managers=managers_data)
    except Exception as e:
        logger.error(f"Error listing survey managers: {e}", exc_info=True)
        flash('خطا در نمایش لیست مسئولین نظرسنجی', 'error')
        return redirect(url_for('admin.index'))


@admin_bp.route('/survey/managers/create', methods=['GET', 'POST'])
@admin_required
def survey_managers_create():
    """Create a new survey manager"""
    if request.method == 'POST':
        try:
            user_sso_id = request.form.get('user_sso_id', '').strip()
            if not user_sso_id:
                flash('لطفاً شناسه کاربری (SSO ID) را وارد کنید', 'error')
                return render_template('admin/survey/managers/create.html')
            
            # Find user by SSO ID
            user = User.query.filter_by(sso_id=user_sso_id.lower()).first()
            if not user:
                flash('کاربری با این شناسه کاربری یافت نشد', 'error')
                return render_template('admin/survey/managers/create.html')
            
            # Check if user is already a manager
            existing = SurveyManager.query.filter_by(user_id=user.id).first()
            if existing:
                flash('این کاربر قبلاً به عنوان مسئول نظرسنجی تعریف شده است', 'error')
                return render_template('admin/survey/managers/create.html')
            
            # Create new manager
            manager = SurveyManager(
                user_id=user.id,
                is_active=True,
                created_by=current_user.id
            )
            db.session.add(manager)
            db.session.commit()
            
            log_action('create_survey_manager', 'survey_manager', manager.id, {
                'user_id': user.id,
                'user_sso_id': user_sso_id
            })
            flash('مسئول نظرسنجی با موفقیت ایجاد شد', 'success')
            return redirect(url_for('admin.survey_managers_list'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating survey manager: {e}", exc_info=True)
            flash('خطا در ایجاد مسئول نظرسنجی', 'error')
            return render_template('admin/survey/managers/create.html')
    
    return render_template('admin/survey/managers/create.html')


@admin_bp.route('/survey/managers/<int:manager_id>/toggle', methods=['POST'])
@admin_required
def survey_managers_toggle(manager_id):
    """Toggle active/inactive status of a survey manager"""
    try:
        manager = SurveyManager.query.get_or_404(manager_id)
        manager.is_active = not manager.is_active
        db.session.commit()
        
        log_action('toggle_survey_manager', 'survey_manager', manager_id, {
            'is_active': manager.is_active
        })
        
        return jsonify({
            'success': True,
            'is_active': manager.is_active,
            'message': 'وضعیت مسئول نظرسنجی با موفقیت تغییر کرد'
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error toggling survey manager: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': 'خطا در تغییر وضعیت'
        }), 500


@admin_bp.route('/survey/managers/<int:manager_id>/delete', methods=['POST'])
@admin_required
def survey_managers_delete(manager_id):
    """Delete a survey manager"""
    try:
        manager = SurveyManager.query.get_or_404(manager_id)
        
        # Check if manager has any surveys
        survey_count = Survey.query.filter_by(manager_id=manager_id).count()
        if survey_count > 0:
            return jsonify({
                'success': False,
                'message': f'این مسئول دارای {survey_count} پرسشنامه است. ابتدا پرسشنامه‌ها را حذف یا منتقل کنید.'
            }), 400
        
        db.session.delete(manager)
        db.session.commit()
        
        log_action('delete_survey_manager', 'survey_manager', manager_id)
        return jsonify({
            'success': True,
            'message': 'مسئول نظرسنجی با موفقیت حذف شد'
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting survey manager: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': 'خطا در حذف مسئول نظرسنجی'
        }), 500


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
                import os
                if 'logo' in request.files:
                    logo_file = request.files['logo']
                    if logo_file and logo_file.filename:
                        from survey.utils import validate_file_upload
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
        
        if not question_text:
            return jsonify({'success': False, 'message': 'متن سوال الزامی است'}), 400
        
        from survey_models import SurveyQuestion
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

