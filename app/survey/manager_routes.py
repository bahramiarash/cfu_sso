"""
Survey Manager Routes
Routes for survey managers to create and manage surveys
"""
from flask import render_template, request, jsonify, redirect, url_for, flash, session, send_file, make_response, send_from_directory, abort
from flask_login import current_user, login_required
from . import survey_bp
from .utils import log_survey_action, sanitize_input, is_survey_manager
from models import User
from survey_models import (
    SurveyManager, Survey, SurveyCategory, SurveyQuestion,
    SurveyAccessGroup, SurveyAllowedUser, SurveyResponse, SurveyAnswerItem,
    SurveyParameter, SurveyResponseParameter
)
from extensions import db
from sqlalchemy import desc, func, cast, Date
from datetime import datetime, timedelta
from jdatetime import datetime as jdatetime
import logging
import json
import os
import io
import zipfile
import requests
import shutil
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

try:
    import qrcode
    from PIL import Image, ImageDraw, ImageFont
    import arabic_reshaper
    from bidi.algorithm import get_display
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False

def reshape_rtl(text):
    """Reshape and display RTL text (Persian/Arabic) correctly"""
    try:
        reshaped = arabic_reshaper.reshape(str(text))
        return get_display(reshaped)
    except:
        return str(text)


def download_b_nazanin_font():
    """Download B Nazanin font if not available"""
    windows_font_dir = "C:/Windows/Fonts"
    downloaded = False
    
    # Check if font directory exists
    if not os.path.exists(windows_font_dir):
        logger.warning(f"Font directory not found: {windows_font_dir}")
        return False
    
    # Font download URLs - using reliable sources
    # Note: B Nazanin is a Persian font, we'll try multiple sources
    font_sources = [
        {
            'bold': 'https://github.com/rastikerdar/b-nazanin-font/raw/master/dist/B%20Nazanin%20Bold.ttf',
            'regular': 'https://github.com/rastikerdar/b-nazanin-font/raw/master/dist/B%20Nazanin.ttf'
        },
        {
            'bold': 'https://raw.githubusercontent.com/rastikerdar/b-nazanin-font/master/dist/B%20Nazanin%20Bold.ttf',
            'regular': 'https://raw.githubusercontent.com/rastikerdar/b-nazanin-font/master/dist/B%20Nazanin.ttf'
        }
    ]
    
    # Try to download B Nazanin Bold
    bold_path = os.path.join(windows_font_dir, "BNazaninBold.ttf")
    if not os.path.exists(bold_path):
        for source_idx, source in enumerate(font_sources):
            try:
                logger.info(f"Downloading B Nazanin Bold font from source {source_idx + 1}...")
                response = requests.get(source['bold'], timeout=30, stream=True, allow_redirects=True)
                if response.status_code == 200:
                    with open(bold_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    logger.info(f"Successfully downloaded B Nazanin Bold to {bold_path}")
                    downloaded = True
                    break
                else:
                    logger.warning(f"Failed to download Bold from source {source_idx + 1}, status: {response.status_code}")
            except Exception as e:
                logger.warning(f"Error downloading Bold from source {source_idx + 1}: {e}")
                continue
    
    # Try to download B Nazanin Regular
    regular_path = os.path.join(windows_font_dir, "BNazanin.ttf")
    if not os.path.exists(regular_path):
        for source_idx, source in enumerate(font_sources):
            try:
                logger.info(f"Downloading B Nazanin Regular font from source {source_idx + 1}...")
                response = requests.get(source['regular'], timeout=30, stream=True, allow_redirects=True)
                if response.status_code == 200:
                    with open(regular_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    logger.info(f"Successfully downloaded B Nazanin Regular to {regular_path}")
                    downloaded = True
                    break
                else:
                    logger.warning(f"Failed to download Regular from source {source_idx + 1}, status: {response.status_code}")
            except Exception as e:
                logger.warning(f"Error downloading Regular from source {source_idx + 1}: {e}")
                continue
    
    return downloaded

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
        
        # Get manager's surveys with completion counts
        surveys_query = Survey.query.filter_by(manager_id=manager.id).order_by(desc(Survey.created_at))
        surveys = surveys_query.all()
        
        # Prepare surveys data with completion counts
        surveys_data = []
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
            
            # Add completion count to survey data
            surveys_data.append({
                'survey': survey,
                'completed_count': completed
            })
        
        log_survey_action('view_manager_dashboard', 'survey_manager', manager.id)
        return render_template('survey/manager/dashboard.html', 
                             manager=manager,
                             surveys=surveys_data,
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
            
            # Date parsing (Jalali to Gregorian)
            start_date = None
            end_date = None
            if request.form.get('start_date'):
                try:
                    # Parse Jalali date (format: YYYY/MM/DD)
                    jalali_str = request.form.get('start_date').strip()
                    if jalali_str:
                        jalali_parts = list(map(int, jalali_str.split('/')))
                        jalali_dt = jdatetime.datetime(jalali_parts[0], jalali_parts[1], jalali_parts[2])
                        start_date = jalali_dt.togregorian()
                except Exception as e:
                    logger.warning(f"Error parsing start_date: {e}")
                    pass
            
            if request.form.get('end_date'):
                try:
                    # Parse Jalali date (format: YYYY/MM/DD)
                    jalali_str = request.form.get('end_date').strip()
                    if jalali_str:
                        jalali_parts = list(map(int, jalali_str.split('/')))
                        jalali_dt = jdatetime.datetime(jalali_parts[0], jalali_parts[1], jalali_parts[2])
                        end_date = jalali_dt.togregorian()
                except Exception as e:
                    logger.warning(f"Error parsing end_date: {e}")
                    pass
            
            # Handle anonymous access password
            anonymous_password = None
            access_type = request.form.get('access_type', 'public')
            if access_type == 'anonymous':
                anonymous_password_raw = request.form.get('anonymous_access_password', '').strip()
                if anonymous_password_raw:
                    # Hash the password using hashlib
                    import hashlib
                    anonymous_password = hashlib.sha256(anonymous_password_raw.encode()).hexdigest()
            
            # Create survey
            survey = Survey(
                title=title,
                description=description,
                manager_id=manager.id,
                start_date=start_date,
                end_date=end_date,
                status=request.form.get('status', 'active'),
                access_type=access_type,
                anonymous_access_password=anonymous_password,
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
            
            # Handle survey parameters (only for anonymous surveys)
            if survey.access_type == 'anonymous':
                # Get existing parameter IDs to track which ones to keep
                parameter_names = request.form.getlist('parameter_name[]')
                parameter_values_list = request.form.getlist('parameter_values[]')
                parameter_ids = request.form.getlist('parameter_id[]')
                
                # Delete parameters that are not in the form (for edit mode)
                existing_params = {p.id: p for p in SurveyParameter.query.filter_by(survey_id=survey.id).all()}
                submitted_param_ids = [int(pid) for pid in parameter_ids if pid and pid.strip()]
                
                for param_id, param in existing_params.items():
                    if param_id not in submitted_param_ids:
                        db.session.delete(param)
                
                # Add or update parameters
                for idx, (param_name, param_values_str) in enumerate(zip(parameter_names, parameter_values_list)):
                    if not param_name or not param_values_str:
                        continue
                    
                    param_name = param_name.strip()
                    param_values = [v.strip() for v in param_values_str.split(',') if v.strip()]
                    
                    if not param_name or not param_values:
                        continue
                    
                    param_id = parameter_ids[idx] if idx < len(parameter_ids) and parameter_ids[idx] else None
                    
                    if param_id and param_id.strip():
                        # Update existing parameter
                        try:
                            param = SurveyParameter.query.get(int(param_id))
                            if param and param.survey_id == survey.id:
                                param.parameter_name = param_name
                                param.parameter_values = param_values
                                param.order = idx + 1
                        except (ValueError, AttributeError):
                            pass
                    else:
                        # Create new parameter
                        param = SurveyParameter(
                            survey_id=survey.id,
                            parameter_name=param_name,
                            parameter_values=param_values,
                            order=idx + 1
                        )
                        db.session.add(param)
            else:
                # Delete all parameters if access type is not anonymous
                SurveyParameter.query.filter_by(survey_id=survey.id).delete()
            
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
            
            # Handle anonymous access password
            if survey.access_type == 'anonymous':
                anonymous_password = request.form.get('anonymous_access_password', '').strip()
                if anonymous_password:
                    # Hash the password using hashlib
                    import hashlib
                    survey.anonymous_access_password = hashlib.sha256(anonymous_password.encode()).hexdigest()
                else:
                    # If password is empty, clear it
                    survey.anonymous_access_password = None
            else:
                # Clear password if access type is not anonymous
                survey.anonymous_access_password = None
            
            survey.max_completions_per_user = int(request.form.get('max_completions_per_user', 1))
            survey.completion_period_type = request.form.get('completion_period_type', 'yearly')
            survey.welcome_message = sanitize_input(request.form.get('welcome_message', '').strip())
            survey.welcome_button_text = sanitize_input(request.form.get('welcome_button_text', 'شروع نظرسنجی').strip())
            survey.display_mode = request.form.get('display_mode', 'multi_page')
            
            # Date parsing (Jalali to Gregorian)
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
                                try:
                                    os.remove(old_path)
                                except Exception as e:
                                    logger.warning(f"Error deleting old logo: {e}")
                        
                        # Save new logo
                        upload_dir = os.path.join('app', 'static', 'uploads', 'surveys', 'logos')
                        os.makedirs(upload_dir, exist_ok=True)
                        logo_filename = f"survey_{survey.id}_{logo_file.filename}"
                        logo_path = os.path.join(upload_dir, logo_filename)
                        logo_file.save(logo_path)
                        survey.logo_path = f"/static/uploads/surveys/logos/{logo_filename}"
            
            # Handle survey parameters (only for anonymous surveys)
            if survey.access_type == 'anonymous':
                # Get existing parameter IDs to track which ones to keep
                parameter_names = request.form.getlist('parameter_name[]')
                parameter_values_list = request.form.getlist('parameter_values[]')
                parameter_ids = request.form.getlist('parameter_id[]')
                
                # Delete parameters that are not in the form
                existing_params = {p.id: p for p in SurveyParameter.query.filter_by(survey_id=survey.id).all()}
                submitted_param_ids = [int(pid) for pid in parameter_ids if pid and pid.strip()]
                
                for param_id, param in existing_params.items():
                    if param_id not in submitted_param_ids:
                        db.session.delete(param)
                
                # Add or update parameters
                for idx, (param_name, param_values_str) in enumerate(zip(parameter_names, parameter_values_list)):
                    if not param_name or not param_values_str:
                        continue
                    
                    param_name = param_name.strip()
                    param_values = [v.strip() for v in param_values_str.split(',') if v.strip()]
                    
                    if not param_name or not param_values:
                        continue
                    
                    param_id = parameter_ids[idx] if idx < len(parameter_ids) and parameter_ids[idx] else None
                    
                    if param_id and param_id.strip():
                        # Update existing parameter
                        try:
                            param = SurveyParameter.query.get(int(param_id))
                            if param and param.survey_id == survey.id:
                                param.parameter_name = param_name
                                param.parameter_values = param_values
                                param.order = idx + 1
                        except (ValueError, AttributeError):
                            pass
                    else:
                        # Create new parameter
                        param = SurveyParameter(
                            survey_id=survey.id,
                            parameter_name=param_name,
                            parameter_values=param_values,
                            order=idx + 1
                        )
                        db.session.add(param)
            else:
                # Delete all parameters if access type is not anonymous
                SurveyParameter.query.filter_by(survey_id=survey.id).delete()
            
            db.session.commit()
            
            log_survey_action('edit_survey', 'survey', survey_id)
            flash('پرسشنامه با موفقیت به‌روزرسانی شد', 'success')
            return redirect(url_for('survey.manager_surveys_list'))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error editing survey: {e}", exc_info=True)
            flash('خطا در به‌روزرسانی پرسشنامه', 'error')
    
    # Generate anonymous access link if access_type is anonymous
    anonymous_access_link = None
    if survey.access_type == 'anonymous':
        # Import hashlib and generate hash directly (same logic as in public_routes)
        import hashlib
        ANONYMOUS_ACCESS_SECRET = "cfu_survey_anonymous_2024"
        data = f"{survey.id}_{ANONYMOUS_ACCESS_SECRET}"
        hash_value = hashlib.sha256(data.encode()).hexdigest()[:16]
        # Build URL with correct host (bi.cfu.ac.ir instead of localhost:5006)
        # Get host from request or use default
        host = request.host
        scheme = request.scheme
        
        # Replace localhost with bi.cfu.ac.ir
        if 'localhost' in host or '127.0.0.1' in host:
            host = 'bi.cfu.ac.ir'
            scheme = 'https'  # Use HTTPS for production
        
        anonymous_access_link = f"{scheme}://{host}{url_for('survey.survey_start', survey_id=survey.id, hash=hash_value)}"
    
    # Get survey parameters
    survey_parameters = SurveyParameter.query.filter_by(survey_id=survey.id).order_by(SurveyParameter.order).all()
    
    return render_template('survey/manager/surveys/edit.html', 
                         survey=survey, 
                         anonymous_access_link=anonymous_access_link,
                         survey_parameters=survey_parameters)


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
        option_display_type = data.get('option_display_type', 'radio')  # Default to radio
        text_input_type = data.get('text_input_type', 'multi_line')  # Default to multi_line
        validation_type = data.get('validation_type')  # Can be None, 'national_id', 'email', 'landline', 'mobile', 'website'
        
        if not question_text:
            return jsonify({'success': False, 'message': 'متن سوال الزامی است'}), 400
        
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


def _get_filtered_responses_query(survey_id, date_from=None, date_to=None):
    """Helper function to get filtered responses query"""
    query = SurveyResponse.query.filter_by(survey_id=survey_id)
    
    # Filter by date range if provided
    if date_from:
        try:
            jdate_from = jdatetime.strptime(date_from, '%Y/%m/%d')
            date_from_greg = jdate_from.togregorian()
            query = query.filter(SurveyResponse.started_at >= date_from_greg)
        except:
            pass
    
    if date_to:
        try:
            jdate_to = jdatetime.strptime(date_to, '%Y/%m/%d')
            date_to_greg = jdate_to.togregorian()
            date_to_greg = datetime.combine(date_to_greg.date(), datetime.max.time())
            query = query.filter(SurveyResponse.started_at <= date_to_greg)
        except:
            pass
    
    return query

@survey_bp.route('/manager/surveys/<int:survey_id>/reports/overview')
@login_required
@manager_required
def manager_reports_overview(survey_id):
    """Survey reports overview - Main page with links to different report sections"""
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
        
        # Get basic statistics only
        query = _get_filtered_responses_query(survey_id, date_from, date_to)
        
        total_responses = query.count()
        completed_responses = query.filter_by(is_completed=True).count()
        attempted_responses = query.filter_by(is_completed=False).count()
        
        # Get survey parameters for anonymous surveys
        survey_parameters = []
        if survey.access_type == 'anonymous':
            survey_parameters = SurveyParameter.query.filter_by(survey_id=survey_id).order_by(SurveyParameter.order).all()
        
        log_survey_action('view_survey_reports', 'survey', survey_id)
        return render_template('survey/manager/reports/overview_index.html',
                             survey=survey,
                             total_responses=total_responses,
                             completed_responses=completed_responses,
                             attempted_responses=attempted_responses,
                             survey_parameters=survey_parameters,
                             date_from=date_from,
                             date_to=date_to)
    except Exception as e:
        logger.error(f"Error viewing reports: {e}", exc_info=True)
        flash('خطا در نمایش گزارش‌ها', 'error')
        return redirect(url_for('survey.manager_surveys_list'))


def _get_daily_chart_data(survey_id, survey, date_from=None, date_to=None):
    """Helper function to get daily completion chart data"""
    daily_chart_data = []
    try:
        # Determine date range
            chart_start_date = None
            chart_end_date = None
            
            if date_from:
                try:
                    jdate_from = jdatetime.strptime(date_from, '%Y/%m/%d')
                    chart_start_date = jdate_from.togregorian().date()
                except Exception as e:
                    logger.warning(f"Error parsing date_from: {e}")
            
            if date_to:
                try:
                    jdate_to = jdatetime.strptime(date_to, '%Y/%m/%d')
                    chart_end_date = jdate_to.togregorian().date()
                except Exception as e:
                    logger.warning(f"Error parsing date_to: {e}")
            
            # If no date range specified, use survey dates or response dates
            if not chart_start_date:
                if survey.start_date:
                    chart_start_date = survey.start_date.date()
                else:
                    # Get earliest response date
                    earliest = db.session.query(func.min(SurveyResponse.started_at)).filter_by(
                        survey_id=survey_id
                    ).scalar()
                    if earliest:
                        chart_start_date = earliest.date() if isinstance(earliest, datetime) else earliest
                    else:
                        chart_start_date = datetime.now().date()
            
            if not chart_end_date:
                if survey.end_date:
                    chart_end_date = survey.end_date.date()
                else:
                    # Get latest response date or today
                    latest = db.session.query(func.max(SurveyResponse.completed_at)).filter_by(
                        survey_id=survey_id,
                        is_completed=True
                    ).scalar()
                    if latest:
                        chart_end_date = latest.date() if isinstance(latest, datetime) else latest
                    else:
                        chart_end_date = datetime.now().date()
            
            # Get actual completion counts per day
            # Convert chart dates to datetime for comparison
            chart_start_datetime = datetime.combine(chart_start_date, datetime.min.time())
            chart_end_datetime = datetime.combine(chart_end_date, datetime.max.time())
            
            # Get all completed responses in date range
            completed_responses_list = SurveyResponse.query.filter(
                SurveyResponse.survey_id == survey_id,
                SurveyResponse.is_completed == True,
                SurveyResponse.completed_at.isnot(None),
                SurveyResponse.completed_at >= chart_start_datetime,
                SurveyResponse.completed_at <= chart_end_datetime
            ).all()
            
            # Group by date manually (more reliable than SQL date functions)
            counts_by_date = {}
            for response in completed_responses_list:
                if response.completed_at:
                    # Extract date part (handle both datetime and date objects)
                    if isinstance(response.completed_at, datetime):
                        resp_date = response.completed_at.date()
                    else:
                        resp_date = response.completed_at
                    
                    # Only count if within our chart range
                    if chart_start_date <= resp_date <= chart_end_date:
                        counts_by_date[resp_date] = counts_by_date.get(resp_date, 0) + 1
            
            logger.info(f"Daily stats: Found {len(completed_responses_list)} completed responses, grouped into {len(counts_by_date)} days")
            
            # Generate data for all days in range (including days with 0 completions)
            # Limit to 365 days to prevent performance issues
            days_diff = (chart_end_date - chart_start_date).days
            if days_diff > 365:
                # If range is too large, limit to last 365 days
                chart_start_date = chart_end_date - timedelta(days=365)
                logger.warning(f"Date range too large ({days_diff} days), limiting to last 365 days")
            
            current_date = chart_start_date
            while current_date <= chart_end_date:
                try:
                    jdate = jdatetime.fromgregorian(date=current_date)
                    count = counts_by_date.get(current_date, 0)
                    daily_chart_data.append({
                        'date': jdate.strftime('%Y/%m/%d'),
                        'count': count
                    })
                except Exception as e:
                    logger.warning(f"Error converting date to Jalali: {e}")
                
                current_date += timedelta(days=1)
                
    except Exception as e:
        logger.error(f"Error getting daily stats: {e}", exc_info=True)
        daily_chart_data = []
    
    return daily_chart_data


@survey_bp.route('/manager/surveys/<int:survey_id>/reports/daily-chart')
@login_required
@manager_required
def manager_reports_daily_chart(survey_id):
    """Daily completion chart page"""
    try:
        manager = SurveyManager.query.filter_by(user_id=current_user.id, is_active=True).first()
        if not manager:
            flash('شما به عنوان مسئول نظرسنجی تعریف نشده‌اید', 'error')
            return redirect(url_for('list_tools'))
        
        survey = Survey.query.get_or_404(survey_id)
        if survey.manager_id != manager.id:
            flash('شما دسترسی به این پرسشنامه ندارید', 'error')
            return redirect(url_for('survey.manager_surveys_list'))
        
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        daily_chart_data = _get_daily_chart_data(survey_id, survey, date_from, date_to)
        
        log_survey_action('view_daily_chart', 'survey', survey_id)
        return render_template('survey/manager/reports/daily_chart.html',
                             survey=survey,
                             daily_chart_data=daily_chart_data,
                             date_from=date_from,
                             date_to=date_to)
    except Exception as e:
        logger.error(f"Error viewing daily chart: {e}", exc_info=True)
        flash('خطا در نمایش نمودار', 'error')
        return redirect(url_for('survey.manager_reports_overview', survey_id=survey_id))


@survey_bp.route('/manager/surveys/<int:survey_id>/reports/participants')
@login_required
@manager_required
def manager_reports_participants(survey_id):
    """Participants table page"""
    try:
        manager = SurveyManager.query.filter_by(user_id=current_user.id, is_active=True).first()
        if not manager:
            flash('شما به عنوان مسئول نظرسنجی تعریف نشده‌اید', 'error')
            return redirect(url_for('list_tools'))
        
        survey = Survey.query.get_or_404(survey_id)
        if survey.manager_id != manager.id:
            flash('شما دسترسی به این پرسشنامه ندارید', 'error')
            return redirect(url_for('survey.manager_surveys_list'))
        
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        query = _get_filtered_responses_query(survey_id, date_from, date_to)
        all_responses = query.order_by(
            desc(SurveyResponse.completed_at),
            desc(SurveyResponse.started_at)
        ).all()
        
        # Get parameters for each response
        response_parameters_dict = {}
        if survey.access_type == 'anonymous':
            for response in all_responses:
                response_params = SurveyResponseParameter.query.filter_by(response_id=response.id).all()
                params_dict = {}
                for rp in response_params:
                    if rp.parameter:
                        params_dict[rp.parameter.parameter_name] = rp.parameter_value
                response_parameters_dict[response.id] = params_dict
        
        log_survey_action('view_participants', 'survey', survey_id)
        return render_template('survey/manager/reports/participants.html',
                             survey=survey,
                             all_responses=all_responses,
                             response_parameters_dict=response_parameters_dict,
                             date_from=date_from,
                             date_to=date_to)
    except Exception as e:
        logger.error(f"Error viewing participants: {e}", exc_info=True)
        flash('خطا در نمایش جدول شرکت کنندگان', 'error')
        return redirect(url_for('survey.manager_reports_overview', survey_id=survey_id))


def _get_question_stats(survey_id, date_from=None, date_to=None):
    """Helper function to get question statistics grouped by category"""
    from survey_models import SurveyQuestion, SurveyAnswerItem
    question_stats_by_category = []
    question_stats_json = []
    
    try:
        # Get all categories for this survey, ordered by order field
        categories = SurveyCategory.query.filter_by(survey_id=survey_id).order_by(SurveyCategory.order).all()
        
        # Process questions for each category
        for category in categories:
            category_questions = SurveyQuestion.query.filter_by(
                survey_id=survey_id,
                category_id=category.id
            ).order_by(SurveyQuestion.order).all()
            
            category_question_stats = []
            
            for question in category_questions:
                try:
                    # Get all answers for this question
                    answers_query = db.session.query(SurveyAnswerItem).join(
                        SurveyResponse
                    ).filter(
                        SurveyAnswerItem.question_id == question.id,
                        SurveyResponse.survey_id == survey_id,
                        SurveyResponse.is_completed == True
                    )
                    
                    if date_from:
                        try:
                            jdate_from = jdatetime.strptime(date_from, '%Y/%m/%d')
                            date_from_greg = jdate_from.togregorian()
                            answers_query = answers_query.filter(SurveyResponse.completed_at >= date_from_greg)
                        except Exception as e:
                            logger.warning(f"Error parsing date_from for question stats: {e}")
                    
                    if date_to:
                        try:
                            jdate_to = jdatetime.strptime(date_to, '%Y/%m/%d')
                            date_to_greg = jdate_to.togregorian()
                            date_to_greg = datetime.combine(date_to_greg.date(), datetime.max.time())
                            answers_query = answers_query.filter(SurveyResponse.completed_at <= date_to_greg)
                        except Exception as e:
                            logger.warning(f"Error parsing date_to for question stats: {e}")
                    
                    answers = answers_query.all()
                    
                    # Count answers by option/value
                    option_counts_ordered = []
                    options_list = []
                    
                    if question.question_type.startswith('likert'):
                        if question.options:
                            if isinstance(question.options, dict):
                                options_list = question.options.get('options', [])
                            elif isinstance(question.options, list):
                                options_list = question.options
                            else:
                                options_list = []
                        else:
                            options_list = []
                        
                        for i, option in enumerate(options_list):
                            count = sum(1 for a in answers if a.answer_value == i)
                            option_counts_ordered.append({
                                'option': option,
                                'count': count,
                                'index': i
                            })
                    else:
                        option_counts_ordered.append({
                            'option': 'پاسخ داده شده',
                            'count': len(answers),
                            'index': 0
                        })
                    
                    option_counts = {item['option']: item['count'] for item in option_counts_ordered}
                    
                    question_stat = {
                        'question': question,
                        'total_answers': len(answers),
                        'option_counts': option_counts,
                        'option_counts_ordered': option_counts_ordered
                    }
                    category_question_stats.append(question_stat)
                    
                    question_stats_json.append({
                        'question_id': question.id,
                        'question_text': question.question_text,
                        'total_answers': len(answers),
                        'option_counts': option_counts,
                        'option_counts_ordered': option_counts_ordered
                    })
                except Exception as e:
                    logger.error(f"Error processing question {question.id}: {e}", exc_info=True)
                    continue
            
            if category_question_stats:
                question_stats_by_category.append({
                    'category': category,
                    'questions': category_question_stats
                })
        
        # Process questions without category
        questions_without_category = SurveyQuestion.query.filter_by(
            survey_id=survey_id
        ).filter(
            SurveyQuestion.category_id.is_(None)
        ).order_by(SurveyQuestion.order).all()
        
        if questions_without_category:
            uncategorized_question_stats = []
            
            for question in questions_without_category:
                try:
                    answers_query = db.session.query(SurveyAnswerItem).join(
                        SurveyResponse
                    ).filter(
                        SurveyAnswerItem.question_id == question.id,
                        SurveyResponse.survey_id == survey_id,
                        SurveyResponse.is_completed == True
                    )
                    
                    if date_from:
                        try:
                            jdate_from = jdatetime.strptime(date_from, '%Y/%m/%d')
                            date_from_greg = jdate_from.togregorian()
                            answers_query = answers_query.filter(SurveyResponse.completed_at >= date_from_greg)
                        except Exception as e:
                            logger.warning(f"Error parsing date_from for question stats: {e}")
                    
                    if date_to:
                        try:
                            jdate_to = jdatetime.strptime(date_to, '%Y/%m/%d')
                            date_to_greg = jdate_to.togregorian()
                            date_to_greg = datetime.combine(date_to_greg.date(), datetime.max.time())
                            answers_query = answers_query.filter(SurveyResponse.completed_at <= date_to_greg)
                        except Exception as e:
                            logger.warning(f"Error parsing date_to for question stats: {e}")
                    
                    answers = answers_query.all()
                    
                    option_counts_ordered = []
                    options_list = []
                    
                    if question.question_type.startswith('likert'):
                        if question.options:
                            if isinstance(question.options, dict):
                                options_list = question.options.get('options', [])
                            elif isinstance(question.options, list):
                                options_list = question.options
                            else:
                                options_list = []
                        else:
                            options_list = []
                        
                        for i, option in enumerate(options_list):
                            count = sum(1 for a in answers if a.answer_value == i)
                            option_counts_ordered.append({
                                'option': option,
                                'count': count,
                                'index': i
                            })
                    else:
                        option_counts_ordered.append({
                            'option': 'پاسخ داده شده',
                            'count': len(answers),
                            'index': 0
                        })
                    
                    option_counts = {item['option']: item['count'] for item in option_counts_ordered}
                    
                    question_stat = {
                        'question': question,
                        'total_answers': len(answers),
                        'option_counts': option_counts,
                        'option_counts_ordered': option_counts_ordered
                    }
                    uncategorized_question_stats.append(question_stat)
                    
                    question_stats_json.append({
                        'question_id': question.id,
                        'question_text': question.question_text,
                        'total_answers': len(answers),
                        'option_counts': option_counts,
                        'option_counts_ordered': option_counts_ordered
                    })
                except Exception as e:
                    logger.error(f"Error processing question {question.id}: {e}", exc_info=True)
                    continue
            
            if uncategorized_question_stats:
                from types import SimpleNamespace
                uncategorized_category = SimpleNamespace(
                    id=None,
                    title='سوالات بدون دسته',
                    description=None,
                    order=9999
                )
                question_stats_by_category.append({
                    'category': uncategorized_category,
                    'questions': uncategorized_question_stats
                })
    except Exception as e:
        logger.error(f"Error getting question stats: {e}", exc_info=True)
        question_stats_by_category = []
        question_stats_json = []
    
    return question_stats_by_category, question_stats_json


@survey_bp.route('/manager/surveys/<int:survey_id>/reports/question-charts')
@login_required
@manager_required
def manager_reports_question_charts(survey_id):
    """Question statistics charts page"""
    try:
        manager = SurveyManager.query.filter_by(user_id=current_user.id, is_active=True).first()
        if not manager:
            flash('شما به عنوان مسئول نظرسنجی تعریف نشده‌اید', 'error')
            return redirect(url_for('list_tools'))
        
        survey = Survey.query.get_or_404(survey_id)
        if survey.manager_id != manager.id:
            flash('شما دسترسی به این پرسشنامه ندارید', 'error')
            return redirect(url_for('survey.manager_surveys_list'))
        
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        question_stats_by_category, question_stats_json = _get_question_stats(survey_id, date_from, date_to)
        
        # Get parameter statistics for anonymous surveys
        parameter_charts_data = []
        if survey.access_type == 'anonymous':
            # Get all parameters for this survey
            parameters = SurveyParameter.query.filter_by(survey_id=survey_id).order_by(SurveyParameter.order).all()
            
            for param in parameters:
                # Get all completed responses for this survey
                responses_query = SurveyResponse.query.filter_by(
                    survey_id=survey_id,
                    is_completed=True
                )
                
                # Apply date filters if provided
                if date_from:
                    try:
                        jdate_from = jdatetime.strptime(date_from, '%Y/%m/%d')
                        date_from_greg = jdate_from.togregorian()
                        responses_query = responses_query.filter(SurveyResponse.completed_at >= date_from_greg)
                    except Exception as e:
                        logger.warning(f"Error parsing date_from for parameter stats: {e}")
                
                if date_to:
                    try:
                        jdate_to = jdatetime.strptime(date_to, '%Y/%m/%d')
                        date_to_greg = jdate_to.togregorian()
                        date_to_greg = datetime.combine(date_to_greg.date(), datetime.max.time())
                        responses_query = responses_query.filter(SurveyResponse.completed_at <= date_to_greg)
                    except Exception as e:
                        logger.warning(f"Error parsing date_to for parameter stats: {e}")
                
                completed_responses = responses_query.all()
                
                # Count occurrences of each parameter value
                value_counts = {}
                for response in completed_responses:
                    # Get parameter value for this response
                    response_param = SurveyResponseParameter.query.filter_by(
                        response_id=response.id,
                        parameter_id=param.id
                    ).first()
                    
                    if response_param:
                        param_value = response_param.parameter_value
                        value_counts[param_value] = value_counts.get(param_value, 0) + 1
                
                # Prepare chart data
                if value_counts:
                    # Sort by parameter values (use the order from parameter_values if available)
                    sorted_values = []
                    if param.parameter_values:
                        # Use the order from parameter definition
                        for val in param.parameter_values:
                            if val in value_counts:
                                sorted_values.append({
                                    'value': val,
                                    'count': value_counts[val]
                                })
                        # Add any values not in the definition
                        for val, count in value_counts.items():
                            if val not in [sv['value'] for sv in sorted_values]:
                                sorted_values.append({
                                    'value': val,
                                    'count': count
                                })
                    else:
                        # No predefined order, sort by value
                        for val, count in sorted(value_counts.items()):
                            sorted_values.append({
                                'value': val,
                                'count': count
                            })
                    
                    parameter_charts_data.append({
                        'parameter_name': param.parameter_name,
                        'parameter_id': param.id,
                        'values': sorted_values,
                        'total': sum(value_counts.values())
                    })
        
        log_survey_action('view_question_charts', 'survey', survey_id)
        return render_template('survey/manager/reports/question_charts.html',
                             survey=survey,
                             question_stats_by_category=question_stats_by_category,
                             question_stats_json=question_stats_json,
                             parameter_charts_data=parameter_charts_data,
                             date_from=date_from,
                             date_to=date_to)
    except Exception as e:
        logger.error(f"Error viewing question charts: {e}", exc_info=True)
        flash('خطا در نمایش نمودارها', 'error')
        return redirect(url_for('survey.manager_reports_overview', survey_id=survey_id))


@survey_bp.route('/manager/surveys/<int:survey_id>/reports/question-stats')
@login_required
@manager_required
def manager_reports_question_stats(survey_id):
    """Question statistics table page"""
    try:
        manager = SurveyManager.query.filter_by(user_id=current_user.id, is_active=True).first()
        if not manager:
            flash('شما به عنوان مسئول نظرسنجی تعریف نشده‌اید', 'error')
            return redirect(url_for('list_tools'))
        
        survey = Survey.query.get_or_404(survey_id)
        if survey.manager_id != manager.id:
            flash('شما دسترسی به این پرسشنامه ندارید', 'error')
            return redirect(url_for('survey.manager_surveys_list'))
        
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        question_stats_by_category, _ = _get_question_stats(survey_id, date_from, date_to)
        
        log_survey_action('view_question_stats', 'survey', survey_id)
        return render_template('survey/manager/reports/question_stats.html',
                             survey=survey,
                             question_stats_by_category=question_stats_by_category,
                             date_from=date_from,
                             date_to=date_to)
    except Exception as e:
        logger.error(f"Error viewing question stats: {e}", exc_info=True)
        flash('خطا در نمایش جدول آمار', 'error')
        return redirect(url_for('survey.manager_reports_overview', survey_id=survey_id))


@survey_bp.route('/manager/surveys/<int:survey_id>/reports/export/excel')
@login_required
@manager_required
def manager_reports_export_excel(survey_id):
    """Export survey reports to Excel"""
    if not PANDAS_AVAILABLE:
        flash('کتابخانه pandas برای خروجی Excel نیاز است', 'error')
        return redirect(url_for('survey.manager_reports_overview', survey_id=survey_id))
    
    try:
        manager = SurveyManager.query.filter_by(user_id=current_user.id, is_active=True).first()
        if not manager:
            flash('شما به عنوان مسئول نظرسنجی تعریف نشده‌اید', 'error')
            return redirect(url_for('list_tools'))
        
        survey = Survey.query.get_or_404(survey_id)
        if survey.manager_id != manager.id:
            flash('شما دسترسی به این پرسشنامه ندارید', 'error')
            return redirect(url_for('survey.manager_surveys_list'))
        
        # Get date range from query params
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        # Get all responses
        query = SurveyResponse.query.filter_by(survey_id=survey_id, is_completed=True)
        
        if date_from:
            try:
                jdate_from = jdatetime.strptime(date_from, '%Y/%m/%d')
                date_from_greg = jdate_from.togregorian()
                query = query.filter(SurveyResponse.completed_at >= date_from_greg)
            except:
                pass
        
        if date_to:
            try:
                jdate_to = jdatetime.strptime(date_to, '%Y/%m/%d')
                date_to_greg = jdate_to.togregorian()
                date_to_greg = datetime.combine(date_to_greg.date(), datetime.max.time())
                query = query.filter(SurveyResponse.completed_at <= date_to_greg)
            except:
                pass
        
        responses = query.order_by(desc(SurveyResponse.completed_at)).all()
        
        # Get questions
        questions = SurveyQuestion.query.filter_by(survey_id=survey_id).order_by(SurveyQuestion.order).all()
        
        # Prepare data for Excel
        excel_data = {}
        
        # Sheet 1: Participants summary
        participants_data = []
        for response in responses:
            jdate_started = jdatetime.fromgregorian(datetime=response.started_at) if response.started_at else None
            jdate_completed = jdatetime.fromgregorian(datetime=response.completed_at) if response.completed_at else None
            
            participants_data.append({
                'شناسه پاسخ': response.id,
                'نام کاربر': response.user.name if response.user else 'نامشخص',
                'کد ملی': response.national_id or 'نامشخص',
                'تاریخ شروع (هجری شمسی)': jdate_started.strftime('%Y/%m/%d %H:%M') if jdate_started else '',
                'تاریخ تکمیل (هجری شمسی)': jdate_completed.strftime('%Y/%m/%d %H:%M') if jdate_completed else '',
                'وضعیت': 'تکمیل شده' if response.is_completed else 'شروع شده'
            })
        
        # Create DataFrames, handling empty data
        if participants_data:
            excel_data['شرکت کنندگان'] = pd.DataFrame(participants_data)
        else:
            excel_data['شرکت کنندگان'] = pd.DataFrame([{
                'شناسه پاسخ': '',
                'نام کاربر': 'داده‌ای یافت نشد',
                'کد ملی': '',
                'تاریخ شروع (هجری شمسی)': '',
                'تاریخ تکمیل (هجری شمسی)': '',
                'وضعیت': ''
            }])
        
        # Sheet 2: Question statistics
        question_stats_data = []
        for question in questions:
            try:
                # Apply date filters to answers query
                answers_query = SurveyAnswerItem.query.join(SurveyResponse).filter(
                    SurveyAnswerItem.question_id == question.id,
                    SurveyResponse.survey_id == survey_id,
                    SurveyResponse.is_completed == True
                )
                
                # Apply date filters if provided
                if date_from:
                    try:
                        jdate_from = jdatetime.strptime(date_from, '%Y/%m/%d')
                        date_from_greg = jdate_from.togregorian()
                        answers_query = answers_query.filter(SurveyResponse.completed_at >= date_from_greg)
                    except Exception as e:
                        logger.warning(f"Error parsing date_from in Excel export: {e}")
                
                if date_to:
                    try:
                        jdate_to = jdatetime.strptime(date_to, '%Y/%m/%d')
                        date_to_greg = jdate_to.togregorian()
                        date_to_greg = datetime.combine(date_to_greg.date(), datetime.max.time())
                        answers_query = answers_query.filter(SurveyResponse.completed_at <= date_to_greg)
                    except Exception as e:
                        logger.warning(f"Error parsing date_to in Excel export: {e}")
                
                answers = answers_query.all()
                
                if question.question_type.startswith('likert'):
                    # Handle both dict format {'options': [...]} and list format [...]
                    if question.options:
                        if isinstance(question.options, dict):
                            options = question.options.get('options', [])
                        elif isinstance(question.options, list):
                            options = question.options
                        else:
                            options = []
                    else:
                        options = []
                    
                    for i, option in enumerate(options):
                        count = sum(1 for a in answers if a.answer_value == i)
                        question_stats_data.append({
                            'سوال': question.question_text[:100] if question.question_text else '',  # Limit length
                            'گزینه': option if option else '',
                            'تعداد پاسخ': count
                        })
                else:
                    question_stats_data.append({
                        'سوال': question.question_text[:100] if question.question_text else '',
                        'گزینه': 'پاسخ داده شده',
                        'تعداد پاسخ': len(answers)
                    })
            except Exception as e:
                logger.error(f"Error processing question {question.id} in Excel export: {e}", exc_info=True)
                # Continue with next question
                continue
        
        # Create DataFrames, handling empty data
        if participants_data:
            excel_data['شرکت کنندگان'] = pd.DataFrame(participants_data)
        else:
            excel_data['شرکت کنندگان'] = pd.DataFrame([{
                'شناسه پاسخ': '',
                'نام کاربر': 'داده‌ای یافت نشد',
                'کد ملی': '',
                'تاریخ شروع (هجری شمسی)': '',
                'تاریخ تکمیل (هجری شمسی)': '',
                'وضعیت': ''
            }])
        
        if question_stats_data:
            excel_data['آمار سوالات'] = pd.DataFrame(question_stats_data)
        else:
            excel_data['آمار سوالات'] = pd.DataFrame([{
                'سوال': 'داده‌ای یافت نشد',
                'گزینه': '',
                'تعداد پاسخ': 0
            }])
        
        # Create Excel file in memory
        output = io.BytesIO()
        try:
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                for sheet_name, df in excel_data.items():
                    # Excel sheet names have limitations (max 31 chars, no special chars)
                    # Keep Persian names but ensure they're valid
                    safe_sheet_name = sheet_name[:31] if len(sheet_name) <= 31 else sheet_name[:28] + '...'
                    # Remove invalid characters for Excel sheet names
                    invalid_chars = ['\\', '/', '?', '*', '[', ']', ':']
                    for char in invalid_chars:
                        safe_sheet_name = safe_sheet_name.replace(char, '_')
                    
                    try:
                        df.to_excel(writer, sheet_name=safe_sheet_name, index=False)
                    except Exception as e:
                        logger.error(f"Error writing sheet {safe_sheet_name}: {e}", exc_info=True)
                        # Try with a simpler name
                        simple_name = f"Sheet{list(excel_data.keys()).index(sheet_name) + 1}"
                        df.to_excel(writer, sheet_name=simple_name, index=False)
            
            output.seek(0)
            
            # Create response
            response = make_response(output.read())
            response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            response.headers['Content-Disposition'] = f'attachment; filename=survey_{survey_id}_reports.xlsx'
            
            log_survey_action('export_survey_reports_excel', 'survey', survey_id)
            return response
        except Exception as excel_error:
            logger.error(f"Error creating Excel file in export_excel: {excel_error}", exc_info=True)
            db.session.rollback()
            flash(f'خطا در تولید فایل Excel: {str(excel_error)}', 'error')
            return redirect(url_for('survey.manager_reports_overview', survey_id=survey_id))
        
    except Exception as e:
        logger.error(f"Error exporting Excel: {e}", exc_info=True)
        db.session.rollback()
        flash(f'خطا در خروجی Excel: {str(e)}', 'error')
        return redirect(url_for('survey.manager_reports_overview', survey_id=survey_id))


@survey_bp.route('/manager/surveys/<int:survey_id>/reports/links/excel')
@login_required
@manager_required
def manager_reports_export_links_excel(survey_id):
    """Export all possible survey links with parameter combinations to Excel"""
    try:
        manager = SurveyManager.query.filter_by(user_id=current_user.id, is_active=True).first()
        if not manager:
            flash('شما به عنوان مسئول نظرسنجی تعریف نشده‌اید', 'error')
            return redirect(url_for('list_tools'))
        
        survey = Survey.query.get_or_404(survey_id)
        if survey.manager_id != manager.id:
            flash('شما دسترسی به این پرسشنامه ندارید', 'error')
            return redirect(url_for('survey.manager_surveys_list'))
        
        if survey.access_type != 'anonymous':
            flash('این قابلیت فقط برای پرسشنامه‌های بدون احراز هویت در دسترس است', 'error')
            return redirect(url_for('survey.manager_reports_overview', survey_id=survey_id))
        
        if not PANDAS_AVAILABLE:
            flash('کتابخانه pandas برای خروجی Excel نیاز است', 'error')
            return redirect(url_for('survey.manager_reports_overview', survey_id=survey_id))
        
        # Get all parameters
        parameters = SurveyParameter.query.filter_by(survey_id=survey_id).order_by(SurveyParameter.order).all()
        
        if not parameters:
            flash('هیچ پارامتری برای این پرسشنامه تعریف نشده است', 'error')
            return redirect(url_for('survey.manager_reports_overview', survey_id=survey_id))
        
        # Generate anonymous access hash
        import hashlib
        ANONYMOUS_ACCESS_SECRET = "cfu_survey_anonymous_2024"
        data = f"{survey.id}_{ANONYMOUS_ACCESS_SECRET}"
        hash_value = hashlib.sha256(data.encode()).hexdigest()[:16]
        
        # Build URL with correct host (bi.cfu.ac.ir instead of localhost:5006)
        # Get host from request or use default
        host = request.host
        scheme = request.scheme
        
        # Replace localhost with bi.cfu.ac.ir
        if 'localhost' in host or '127.0.0.1' in host:
            host = 'bi.cfu.ac.ir'
            scheme = 'https'  # Use HTTPS for production
        
        base_url = f"{scheme}://{host}{url_for('survey.survey_start', survey_id=survey_id, hash=hash_value)}"
        
        # Generate all combinations using itertools.product
        import itertools
        from urllib.parse import urlencode, quote
        
        param_names = [p.parameter_name for p in parameters]
        param_values_lists = [p.parameter_values for p in parameters]
        
        # Generate all combinations
        combinations = list(itertools.product(*param_values_lists))
        
        # Create data for Excel with correct column order: ردیف, url, then parameters
        links_data = []
        for idx, combo in enumerate(combinations, start=1):
            # Build URL with parameters using urlencode for proper encoding
            params_dict = {param_names[i]: combo[i] for i in range(len(combo))}
            # Use quote for each value to handle Persian characters properly
            url_params = '&'.join([f"{name}={quote(str(value), safe='')}" for name, value in params_dict.items()])
            full_url = f"{base_url}&{url_params}"
            
            # Create row data with correct order: ردیف, url, then parameters
            row = {'ردیف': idx, 'url': full_url}
            for i, param_name in enumerate(param_names):
                row[param_name] = combo[i]
            
            links_data.append(row)
        
        # Create DataFrame
        if not links_data:
            flash('هیچ ترکیبی برای تولید لینک وجود ندارد', 'error')
            return redirect(url_for('survey.manager_reports_overview', survey_id=survey_id))
        
        # Ensure column order: ردیف, url, then parameters
        column_order = ['ردیف', 'url'] + param_names
        df = pd.DataFrame(links_data)
        df = df[column_order]  # Reorder columns
        
        # Create Excel file in memory
        output = io.BytesIO()
        try:
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Use a safe sheet name (Excel has limitations on sheet names)
                sheet_name = 'Links'  # Simple English name to avoid issues
                df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            output.seek(0)
            
            # Create response
            response = make_response(output.read())
            response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            response.headers['Content-Disposition'] = f'attachment; filename=survey_{survey_id}_links.xlsx'
            
            log_survey_action('export_survey_links_excel', 'survey', survey_id)
            return response
        except Exception as excel_error:
            logger.error(f"Error creating Excel file in export_links: {excel_error}", exc_info=True)
            raise
        
    except Exception as e:
        logger.error(f"Error exporting links Excel: {e}", exc_info=True)
        db.session.rollback()
        flash(f'خطا در تولید فایل Excel: {str(e)}', 'error')
        return redirect(url_for('survey.manager_reports_overview', survey_id=survey_id))


@survey_bp.route('/manager/surveys/<int:survey_id>/reports/links/qr-zip')
@login_required
@manager_required
def manager_reports_export_links_qr_zip(survey_id):
    """Export QR codes for all survey links as ZIP file"""
    try:
        if not QRCODE_AVAILABLE:
            flash('کتابخانه‌های qrcode و PIL برای تولید QR Code نیاز است', 'error')
            return redirect(url_for('survey.manager_reports_overview', survey_id=survey_id))
        
        manager = SurveyManager.query.filter_by(user_id=current_user.id, is_active=True).first()
        if not manager:
            flash('شما به عنوان مسئول نظرسنجی تعریف نشده‌اید', 'error')
            return redirect(url_for('list_tools'))
        
        survey = Survey.query.get_or_404(survey_id)
        if survey.manager_id != manager.id:
            flash('شما دسترسی به این پرسشنامه ندارید', 'error')
            return redirect(url_for('survey.manager_surveys_list'))
        
        if survey.access_type != 'anonymous':
            flash('این قابلیت فقط برای پرسشنامه‌های بدون احراز هویت در دسترس است', 'error')
            return redirect(url_for('survey.manager_reports_overview', survey_id=survey_id))
        
        # Get all parameters
        parameters = SurveyParameter.query.filter_by(survey_id=survey_id).order_by(SurveyParameter.order).all()
        
        if not parameters:
            flash('هیچ پارامتری برای این پرسشنامه تعریف نشده است', 'error')
            return redirect(url_for('survey.manager_reports_overview', survey_id=survey_id))
        
        # Generate anonymous access hash
        import hashlib
        ANONYMOUS_ACCESS_SECRET = "cfu_survey_anonymous_2024"
        data = f"{survey.id}_{ANONYMOUS_ACCESS_SECRET}"
        hash_value = hashlib.sha256(data.encode()).hexdigest()[:16]
        
        # Build URL with correct host (bi.cfu.ac.ir instead of localhost:5006)
        # Get host from request or use default
        host = request.host
        scheme = request.scheme
        
        # Replace localhost with bi.cfu.ac.ir
        if 'localhost' in host or '127.0.0.1' in host:
            host = 'bi.cfu.ac.ir'
            scheme = 'https'  # Use HTTPS for production
        
        base_url = f"{scheme}://{host}{url_for('survey.survey_start', survey_id=survey_id, hash=hash_value)}"
        
        # Generate all combinations using itertools.product
        import itertools
        from urllib.parse import quote
        
        param_names = [p.parameter_name for p in parameters]
        param_values_lists = [p.parameter_values for p in parameters]
        
        # Generate all combinations
        combinations = list(itertools.product(*param_values_lists))
        
        if not combinations:
            flash('هیچ ترکیبی برای تولید لینک وجود ندارد', 'error')
            return redirect(url_for('survey.manager_reports_overview', survey_id=survey_id))
        
        # Create ZIP file in memory
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for idx, combo in enumerate(combinations, start=1):
                # Build URL with parameters
                params_dict = {param_names[i]: combo[i] for i in range(len(combo))}
                url_params = '&'.join([f"{name}={quote(str(value), safe='')}" for name, value in params_dict.items()])
                full_url = f"{base_url}&{url_params}"
                
                # Create QR Code
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10,
                    border=4,
                )
                qr.add_data(full_url)
                qr.make(fit=True)
                qr_img = qr.make_image(fill_color="black", back_color="white")
                
                # A4 size in pixels at 300 DPI: 2480 x 3508
                # Using 200 DPI for smaller file size: 1654 x 2339
                A4_WIDTH = 1654
                A4_HEIGHT = 2339
                
                # Create A4 image with white background
                img = Image.new('RGB', (A4_WIDTH, A4_HEIGHT), color='white')
                draw = ImageDraw.Draw(img)
                
                # Try to load B Nazanin Bold font (doubled size: 100)
                # Prefer B Nazanin Bold, then B Nazanin, then fallback to other fonts
                font_medium = None
                font_size = 100  # Doubled from 50
                
                # List all possible B Nazanin font paths
                b_nazanin_paths = []
                
                # Windows paths - try different naming conventions
                windows_font_dir = "C:/Windows/Fonts"
                if os.path.exists(windows_font_dir):
                    # Try to find B Nazanin fonts by searching the directory
                    try:
                        for font_file in os.listdir(windows_font_dir):
                            font_lower = font_file.lower()
                            if 'nazanin' in font_lower and (font_file.endswith('.ttf') or font_file.endswith('.TTF')):
                                full_path = os.path.join(windows_font_dir, font_file)
                                if 'bold' in font_lower:
                                    b_nazanin_paths.insert(0, full_path)  # Bold first
                                else:
                                    b_nazanin_paths.append(full_path)
                    except Exception as e:
                        logger.warning(f"Error searching Windows fonts directory: {e}")
                
                # Add explicit paths as fallback
                explicit_paths = [
                    "C:/Windows/Fonts/BNazaninBold.ttf",
                    "C:/Windows/Fonts/BNazanin.ttf",
                    "C:/Windows/Fonts/B Nazanin Bold.ttf",
                    "C:/Windows/Fonts/B Nazanin.ttf",
                    "/usr/share/fonts/truetype/nazanin/BNazaninBold.ttf",
                    "/usr/share/fonts/truetype/nazanin/BNazanin.ttf",
                    "/usr/share/fonts/truetype/nazanin/B Nazanin Bold.ttf",
                    "/usr/share/fonts/truetype/nazanin/B Nazanin.ttf",
                ]
                b_nazanin_paths.extend(explicit_paths)
                
                # Try to find B Nazanin font first
                b_nazanin_found = False
                for font_path in b_nazanin_paths:
                    try:
                        if os.path.exists(font_path):
                            font_medium = ImageFont.truetype(font_path, font_size)
                            b_nazanin_found = True
                            logger.info(f"Using B Nazanin font: {font_path}")
                            break
                    except Exception as e:
                        logger.warning(f"Error loading font {font_path}: {e}")
                        continue
                
                # If B Nazanin not found, try to download it
                if not b_nazanin_found:
                    try:
                        logger.info("B Nazanin font not found, attempting to download...")
                        if download_b_nazanin_font():
                            # Retry loading after download
                            for font_path in b_nazanin_paths[:4]:  # Check Windows paths first
                                try:
                                    if os.path.exists(font_path):
                                        font_medium = ImageFont.truetype(font_path, font_size)
                                        b_nazanin_found = True
                                        logger.info(f"Using downloaded B Nazanin font: {font_path}")
                                        break
                                except Exception as e:
                                    logger.warning(f"Error loading downloaded font {font_path}: {e}")
                                    continue
                    except Exception as e:
                        logger.error(f"Error downloading B Nazanin font: {e}")
                
                # If B Nazanin still not found, try fallback fonts
                if not b_nazanin_found:
                    fallback_paths = [
                        "C:/Windows/Fonts/Vazir-Bold.ttf",
                        "C:/Windows/Fonts/Vazir.ttf",
                        "C:/Windows/Fonts/tahoma.ttf",
                        "C:/Windows/Fonts/arial.ttf",
                        "/usr/share/fonts/truetype/tahoma/Tahoma.ttf",
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                        "/System/Library/Fonts/Supplemental/Arial.ttf",
                    ]
                    
                    for font_path in fallback_paths:
                        try:
                            if os.path.exists(font_path):
                                font_medium = ImageFont.truetype(font_path, font_size)
                                logger.warning(f"B Nazanin not found, using fallback font: {font_path}")
                                break
                        except Exception as e:
                            logger.warning(f"Error loading fallback font {font_path}: {e}")
                            continue
                
                if font_medium is None:
                    try:
                        font_medium = ImageFont.load_default()
                        logger.warning("Using default font - B Nazanin not available")
                    except:
                        font_medium = None
                        logger.error("Failed to load any font")
                
                # Calculate positions
                qr_size = 1200  # QR code size (doubled from 600)
                qr_x = (A4_WIDTH - qr_size) // 2
                qr_y = 500  # Adjusted to accommodate title above
                
                # Resize QR code
                qr_img_resized = qr_img.resize((qr_size, qr_size))
                
                # Add title "فرم نظرسنجی" above QR code (with more spacing)
                title_text = reshape_rtl("فرم نظرسنجی")
                if font_medium:
                    title_bbox = draw.textbbox((0, 0), title_text, font=font_medium)
                else:
                    title_bbox = draw.textbbox((0, 0), title_text)
                title_width = title_bbox[2] - title_bbox[0]
                title_x = (A4_WIDTH - title_width) // 2
                title_y = qr_y - 200  # Increased spacing from 100 to 200
                
                if font_medium:
                    draw.text((title_x, title_y), title_text, fill='black', font=font_medium)
                else:
                    draw.text((title_x, title_y), title_text, fill='black')
                
                # Paste QR code onto A4 image
                img.paste(qr_img_resized, (qr_x, qr_y))
                
                # Add parameter values below QR code (only values, each on separate line, centered)
                text_y = qr_y + qr_size + 100
                line_height = 120  # Increased spacing between lines (from 80 to 120)
                
                for i, param_name in enumerate(param_names):
                    param_value = str(combo[i])
                    
                    # Reshape and display RTL text correctly
                    display_text = reshape_rtl(param_value)
                    
                    # Get text bounding box for centering
                    if font_medium:
                        bbox = draw.textbbox((0, 0), display_text, font=font_medium)
                    else:
                        bbox = draw.textbbox((0, 0), display_text)
                    text_width = bbox[2] - bbox[0]
                    text_x = (A4_WIDTH - text_width) // 2
                    
                    if font_medium:
                        draw.text((text_x, text_y), display_text, fill='black', font=font_medium)
                    else:
                        draw.text((text_x, text_y), display_text, fill='black')
                    text_y += line_height
                
                # Save image to BytesIO
                img_buffer = io.BytesIO()
                img.save(img_buffer, format='PNG')
                img_buffer.seek(0)
                
                # Add to ZIP with descriptive filename
                filename_parts = [f"{name}_{combo[i]}" for i, name in enumerate(param_names)]
                filename = f"qr_{idx:04d}_{'_'.join(filename_parts)}.png"
                zip_file.writestr(filename, img_buffer.read())
        
        zip_buffer.seek(0)
        
        # Add Jalali date and time to filename
        now = datetime.now()
        jdate = jdatetime.fromgregorian(datetime=now)
        date_str = jdate.strftime('%Y%m%d')
        time_str = jdate.strftime('%H%M')
        
        # Create response
        response = make_response(zip_buffer.read())
        response.headers['Content-Type'] = 'application/zip'
        response.headers['Content-Disposition'] = f'attachment; filename=survey_{survey_id}_qr_codes_{date_str}_{time_str}.zip'
        
        log_survey_action('export_survey_qr_codes', 'survey', survey_id)
        return response
        
    except Exception as e:
        logger.error(f"Error exporting QR codes ZIP: {e}", exc_info=True)
        db.session.rollback()
        flash(f'خطا در تولید فایل ZIP: {str(e)}', 'error')
        return redirect(url_for('survey.manager_reports_overview', survey_id=survey_id))


@survey_bp.route('/manager/surveys/<int:survey_id>/reports/response/<int:response_id>')
@login_required
@manager_required
def manager_reports_response_detail(survey_id, response_id):
    """View detailed response for a specific user"""
    try:
        manager = SurveyManager.query.filter_by(user_id=current_user.id, is_active=True).first()
        if not manager:
            flash('شما به عنوان مسئول نظرسنجی تعریف نشده‌اید', 'error')
            return redirect(url_for('list_tools'))
        
        survey = Survey.query.get_or_404(survey_id)
        if survey.manager_id != manager.id:
            flash('شما دسترسی به این پرسشنامه ندارید', 'error')
            return redirect(url_for('survey.manager_surveys_list'))
        
        # Get the response
        response = SurveyResponse.query.get_or_404(response_id)
        if response.survey_id != survey_id:
            flash('این پاسخ متعلق به این پرسشنامه نیست', 'error')
            return redirect(url_for('survey.manager_reports_overview', survey_id=survey_id))
        
        # Get all questions with their answers
        questions = SurveyQuestion.query.filter_by(survey_id=survey_id).order_by(SurveyQuestion.order).all()
        
        # Get categories
        categories = SurveyCategory.query.filter_by(survey_id=survey_id).order_by(SurveyCategory.order).all()
        
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
        
        # Get all answers for this response
        answers = {}
        answer_items = SurveyAnswerItem.query.filter_by(response_id=response_id).all()
        for answer_item in answer_items:
            answers[answer_item.question_id] = answer_item
        
        # Get user info
        user = response.user if response.user else None
        user_display_name = user.name if user else (response.national_id or 'کاربر ناشناس')
        
        # Get URL parameters for anonymous surveys
        response_parameters = {}
        if survey.access_type == 'anonymous':
            response_params = SurveyResponseParameter.query.filter_by(response_id=response_id).all()
            for rp in response_params:
                if rp.parameter:
                    response_parameters[rp.parameter.parameter_name] = rp.parameter_value
        
        # Check if current user is admin
        is_admin = False
        try:
            if current_user.is_authenticated and hasattr(current_user, 'is_admin'):
                is_admin = current_user.is_admin()
        except:
            pass
        
        return render_template('survey/manager/reports/response_detail.html',
                             survey=survey,
                             response=response,
                             questions=questions,
                             categories=categories,
                             questions_by_category=questions_by_category,
                             questions_without_category=questions_without_category,
                             answers=answers,
                             user=user,
                             user_display_name=user_display_name,
                             response_parameters=response_parameters,
                             is_admin=is_admin)
        
    except Exception as e:
        logger.error(f"Error viewing response detail: {e}", exc_info=True)
        flash('خطا در نمایش جزئیات پاسخ', 'error')
        return redirect(url_for('survey.manager_reports_overview', survey_id=survey_id))


@survey_bp.route('/uploads/surveys/files/<path:filename>')
@login_required
def survey_uploaded_file(filename):
    """Serve uploaded survey files - requires authentication"""
    try:
        import os
        # Get the app directory (parent of survey directory)
        current_file_dir = os.path.dirname(os.path.abspath(__file__))  # app/survey/
        app_dir = os.path.dirname(current_file_dir)  # app/
        
        # Try multiple possible paths (files are saved relative to working directory)
        possible_paths = [
            os.path.join(app_dir, 'app', 'static', 'uploads', 'surveys', 'files'),  # app/app/static/... (when running from app/)
            os.path.join(app_dir, 'static', 'uploads', 'surveys', 'files'),  # app/static/...
            os.path.join(os.getcwd(), 'app', 'static', 'uploads', 'surveys', 'files'),  # current_dir/app/static/...
            os.path.join(os.getcwd(), 'static', 'uploads', 'surveys', 'files'),  # current_dir/static/...
        ]
        
        upload_dir = None
        file_path = None
        for path in possible_paths:
            test_file = os.path.join(path, filename)
            if os.path.exists(test_file):
                upload_dir = path
                file_path = test_file
                logger.info(f"Found file in: {upload_dir}")
                break
        
        if not upload_dir:
            # Default to the path where files are actually saved (app/app/static/...)
            upload_dir = possible_paths[0]
            file_path = os.path.join(upload_dir, filename)
            logger.warning(f"File not found, using path: {upload_dir}")
        
        # Security: Only allow access to survey managers or admins
        if not current_user.is_authenticated:
            from flask import abort
            abort(401)
        
        # Check if user is survey manager or admin
        is_manager = is_survey_manager(current_user)
        is_admin = False
        try:
            if hasattr(current_user, 'is_admin'):
                is_admin = current_user.is_admin()
        except:
            pass
        
        if not (is_manager or is_admin):
            from flask import abort
            abort(403)
        
        logger.info(f"Serving file: {file_path}, exists: {os.path.exists(file_path)}")
        
        if os.path.exists(file_path):
            return send_from_directory(upload_dir, filename)
        else:
            logger.warning(f"File not found: {file_path}")
            from flask import abort
            abort(404)
    except Exception as e:
        logger.error(f"Error serving file: {e}", exc_info=True)
        from flask import abort
        abort(404)

