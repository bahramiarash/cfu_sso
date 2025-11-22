# routes/tasks.py
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from models import db, Task, KanbanColumn, Project, User
from datetime import datetime

tasks_bp = Blueprint('tasks', __name__)

@tasks_bp.route('/project/<int:project_id>/tasks')
@login_required
def task_list(project_id):
    project = Project.query.get_or_404(project_id)
    if current_user not in project.users:
        flash("You don't have access to this project.", 'danger')
        return redirect(url_for('dashboard'))
    tasks = Task.query.join(KanbanColumn).filter(KanbanColumn.project_id == project_id).all()
    return render_template('tasks/task_list.html', project=project, tasks=tasks)


@tasks_bp.route('/project/<int:project_id>/tasks/create', methods=['GET', 'POST'])
@login_required
def task_create(project_id):
    project = Project.query.get_or_404(project_id)
    if current_user.id not in [project.owner_id, project.creator_id]:
        flash("Only the owner or creator can create tasks.", 'danger')
        return redirect(url_for('tasks.task_list', project_id=project_id))

    columns = KanbanColumn.query.filter_by(project_id=project_id).order_by(KanbanColumn.order).all()
    default_column = next((c for c in columns if c.order == 1), columns[0] if columns else None)

    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        assignee_id = request.form.get('assignee_id')
        due_date = request.form.get('due_date')
        
        if not default_column:
            flash("No column available to assign this task.", 'danger')
            return redirect(url_for('tasks.task_list', project_id=project_id))

        task = Task(
            title=title,
            description=description,
            assignee_id=assignee_id,
            due_date=datetime.strptime(due_date, '%Y-%m-%d') if due_date else None,
            kanban_column_id=default_column.id,
            created_at=datetime.utcnow()
        )
        db.session.add(task)
        db.session.commit()
        flash("Task created successfully.", 'success')
        return redirect(url_for('tasks.task_list', project_id=project_id))

    users = project.users
    return render_template('tasks/task_form.html', project=project, users=users)


@tasks_bp.route('/tasks/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def task_edit(task_id):
    task = Task.query.get_or_404(task_id)
    project = task.kanban_column.project

    user_role = 'other'
    if current_user.id in [project.owner_id, project.creator_id]:
        user_role = 'owner_creator'
    elif current_user in task.assigned_users:
        user_role = 'task_user'
    elif current_user in task.kanban_column.assigned_users:
        user_role = 'column_user'

    if user_role == 'other':
        flash("You don't have permission to edit this task.", 'danger')
        return redirect(url_for('tasks.task_list', project_id=project.id))

    if request.method == 'POST':
        if user_role in ['owner_creator', 'task_user', 'column_user']:
            if user_role != 'column_user' or user_role == 'column_user':
                task.assignee_id = request.form.get('assignee_id')
                task.kanban_column_id = request.form.get('kanban_column_id')
            if user_role in ['owner_creator', 'task_user']:
                task.title = request.form.get('title')
                task.description = request.form.get('description')
                due_date = request.form.get('due_date')
                task.due_date = datetime.strptime(due_date, '%Y-%m-%d') if due_date else None

            db.session.commit()
            flash("Task updated successfully.", 'success')
            return redirect(url_for('tasks.task_list', project_id=project.id))

    columns = KanbanColumn.query.filter_by(project_id=project.id).all()
    users = project.users
    return render_template('tasks/task_form.html', task=task, project=project, users=users, columns=columns, edit=True)
