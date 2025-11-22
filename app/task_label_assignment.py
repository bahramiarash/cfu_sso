# task_label_assignment.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from extensions import db
from models import *
from decorators import admin_or_pm_required

assignment_bp = Blueprint('assignment', __name__, url_prefix='/assignment')

@assignment_bp.route('/tasks/<int:task_id>/labels', methods=['GET', 'POST'])
@login_required
@admin_or_pm_required
def assign_label(task_id):
    task = Task.query.get_or_404(task_id)
    labels = Label.query.all()

    if request.method == 'POST':
        label_id = request.form.get('label_id')
        value_id = request.form.get('value_id')

        # Prevent duplicates
        existing = TaskLabelAssignment.query.filter_by(
            task_id=task_id,
            label_id=label_id
        ).first()
        if existing:
            flash('This label is already assigned to this task. Remove it first to reassign.', 'warning')
        else:
            assignment = TaskLabelAssignment(
                task_id=task_id,
                label_id=label_id,
                label_value_id=value_id
            )
            db.session.add(assignment)
            db.session.commit()
            flash('Label assigned successfully.', 'success')
        return redirect(url_for('assignment.assign_label', task_id=task_id))

    assignments = TaskLabelAssignment.query.filter_by(task_id=task_id).all()
    return render_template('assign_label.html', task=task, labels=labels, assignments=assignments)

@assignment_bp.route('/tasks/<int:task_id>/labels/delete/<int:assignment_id>', methods=['POST'])
@login_required
@admin_or_pm_required
def delete_assignment(task_id, assignment_id):
    assignment = TaskLabelAssignment.query.get_or_404(assignment_id)
    db.session.delete(assignment)
    db.session.commit()
    flash('Label assignment removed.', 'success')
    return redirect(url_for('assignment.assign_label', task_id=task_id))
