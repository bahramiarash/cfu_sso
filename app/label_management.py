# label_management.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from models import Label, LabelValue  

label_bp = Blueprint('labels', __name__, url_prefix='/labels')

# Access control decorator
def admin_or_pm_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.has_role('admin') and not current_user.has_role('project_manager'):
            flash('شما اجازه دسترسی به این بخش را ندارید.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

@label_bp.route('/')
@login_required
@admin_or_pm_required
def list_labels():
    labels = Label.query.all()
    return render_template('labels/list.html', labels=labels)

@label_bp.route('/add', methods=['GET', 'POST'])
@login_required
@admin_or_pm_required
def add_label():
    if request.method == 'POST':
        name = request.form.get('name')
        if name:
            label = Label(name=name)
            db.session.add(label)
            db.session.commit()
            flash('برچسب با موفقیت اضافه شد.', 'success')
            return redirect(url_for('labels.list_labels'))
        flash('نام برچسب نمی‌تواند خالی باشد.', 'danger')
    return render_template('labels/add_label.html')

@label_bp.route('/edit/<int:label_id>', methods=['GET', 'POST'])
@login_required
@admin_or_pm_required
def edit_label(label_id):
    label = Label.query.get_or_404(label_id)
    if request.method == 'POST':
        label.name = request.form.get('name')
        db.session.commit()
        flash('برچسب ویرایش شد.', 'success')
        return redirect(url_for('labels.list_labels'))
    return render_template('labels/edit_label.html', label=label)

@label_bp.route('/delete/<int:label_id>', methods=['POST'])
@login_required
@admin_or_pm_required
def delete_label(label_id):
    label = Label.query.get_or_404(label_id)
    db.session.delete(label)
    db.session.commit()
    flash('برچسب حذف شد.', 'success')
    return redirect(url_for('labels.list_labels'))

@label_bp.route('/<int:label_id>/values')
@login_required
@admin_or_pm_required
def list_values(label_id):
    label = Label.query.get_or_404(label_id)
    return render_template('labels/values/list.html', label=label)

@label_bp.route('/<int:label_id>/values/add', methods=['POST'])
@login_required
@admin_or_pm_required
def add_value(label_id):
    label = Label.query.get_or_404(label_id)
    value = request.form.get('value')
    if value:
        label_value = LabelValue(label_id=label.id, value=value)
        db.session.add(label_value)
        db.session.commit()
        flash('مقدار اضافه شد.', 'success')
    else:
        flash('مقدار نمی‌تواند خالی باشد.', 'danger')
    return redirect(url_for('labels.list_values', label_id=label_id))

@label_bp.route('/values/edit/<int:value_id>', methods=['GET', 'POST'])
@login_required
@admin_or_pm_required
def edit_value(value_id):
    value = LabelValue.query.get_or_404(value_id)
    if request.method == 'POST':
        value.value = request.form.get('value')
        db.session.commit()
        flash('مقدار ویرایش شد.', 'success')
        return redirect(url_for('labels.list_values', label_id=value.label_id))
    return render_template('labels/values/edit_value.html', value=value)

@label_bp.route('/values/delete/<int:value_id>', methods=['POST'])
@login_required
@admin_or_pm_required
def delete_value(value_id):
    value = LabelValue.query.get_or_404(value_id)
    label_id = value.label_id
    db.session.delete(value)
    db.session.commit()
    flash('مقدار حذف شد.', 'success')
    return redirect(url_for('labels.list_values', label_id=label_id))

@label_bp.route('/api/label_values/<int:label_id>')
@login_required
def api_label_values(label_id):
    label = Label.query.get_or_404(label_id)
    return {
        "values": [{"id": v.id, "value": v.value} for v in label.values]
    }
