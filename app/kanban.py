from flask import Blueprint, render_template, redirect, request, session, url_for, flash, g, current_app
from models import db, Project, KanbanColumn, Task, User, TaskAssignedUser, Report
from werkzeug.utils import secure_filename
import os
from flask_login import login_required, current_user
from forms import TaskForm
from forms import TaskEditForm
from forms import ReportForm
from datetime import datetime
import logging
from flask import send_file
import plotly.express as px
import pandas as pd
import jdatetime
import re
from functools import lru_cache
from flask import Response
import json

def to_jalali_string(date_str):
    try:
        # پشتیبانی از رشته‌هایی مثل 2025-06-08 یا 2025/06/08
        if '/' in date_str:
            date_obj = datetime.strptime(date_str, '%Y/%m/%d')
        else:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')

        jalali_date = jdatetime.date.fromgregorian(date=date_obj)
        return f"{jalali_date.year}/{jalali_date.month:02}/{jalali_date.day:02}"
    except Exception as e:
        return "تاریخ نامعتبر"

def convert_jalali_to_gregorian(jalali_str):
    try:
        # پشتیبانی از فرمت YYYY/MM/DD
        parts = [int(p) for p in jalali_str.split('/')]
        if len(parts) != 3:
            raise ValueError("تعداد اجزای تاریخ نامعتبر است.")
        j_date = jdatetime.date(parts[0], parts[1], parts[2])
        return j_date.togregorian()
    except Exception as e:
        print(f"[Jalali Parse Error]: {e}")
        return None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

kanban_bp = Blueprint('kanban', __name__)

readonly_fields = {
    "title": False,
    "description": False,
    "assignee_id": False,
    "due_date": False,
}

@kanban_bp.route('/')
@login_required
def project_list():
    user = g.current_user
    created = Project.query.filter_by(creator_id=user.id).all()
    involved_ids = db.session.query(Project.id).join(KanbanColumn).join(Task).filter(Task.assignee_id == user.id).distinct()
    involved = Project.query.filter(Project.id.in_(involved_ids)).all()
    return render_template('projects.html', created=created, involved=involved)

@kanban_bp.route('/project/new', methods=['GET', 'POST'])
@login_required
def new_project():
    if request.method == 'POST':
        user = current_user
        f = request.files['attachment']
        filename = secure_filename(f.filename)
        f.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))

        project = Project(
            title=request.form['title'],
            description=request.form['description'],
            start_date=request.form['start_date'],
            end_date=request.form['end_date'],
            creator_id=user.id,
            attachment=filename
        )
        project.members.append(user)

        db.session.add(project)
        db.session.commit()

        for i, title in enumerate(['To Do', 'In Progress', 'Done']):
            col = KanbanColumn(project_id=project.id, title=title, order=i)
            db.session.add(col)
        db.session.commit()
        return redirect(url_for('kanban.project_list'))

    return render_template('project_form.html')

@kanban_bp.route('/project/<int:project_id>/export', methods=['GET'])
@login_required
def export_project(project_id):
    project = Project.query.get_or_404(project_id)

    # ✅ Load related data
    columns = KanbanColumn.query.filter_by(project_id=project.id).all()
    tasks = Task.query.filter_by(project_id=project.id).all()

    export_data = {
        "project": {
            "id": project.id,
            "title": project.title,
            "owner_id": project.owner_id,
            "creator_id": project.creator_id,
        },
        "columns": [],
        "tasks": [],
        "reports": [],
        "task_assigned_users": [],
    }

    for col in columns:
        export_data["columns"].append({
            "id": col.id,
            "title": col.title,
            "order": col.order,
            "project_id": col.project_id,
        })

    for task in tasks:
        export_data["tasks"].append({
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "start_date": task.start_date,
            "due_date": task.due_date,
            "project_id": task.project_id,
            "column_id": task.column_id
        })

        for user in task.assigned_users:
            export_data["task_assigned_users"].append({
                "task_id": task.id,
                "user_id": user.id
            })

        for report in task.reports:
            export_data["reports"].append({
                "id": report.id,
                "task_id": report.task_id,
                "user_id": report.user_id,
                "text": report.text,
                "created_at": report.created_at.isoformat()
            })

    # ✅ Convert to JSON and send as download
    json_data = json.dumps(export_data, indent=2, ensure_ascii=False)

    file_name = f"project_{project.id}_export.json"
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file_name)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(json_data)

    return send_file(file_path, as_attachment=True, download_name=file_name, mimetype='application/json')

@kanban_bp.route('/project/<int:project_id>/gantt')
@login_required
def gantt_chart(project_id):
    project = Project.query.get_or_404(project_id)
    tasks = Task.query.filter_by(project_id=project.id).all()

    # Precompiled regex patterns
    jalali_re = re.compile(r"^\d{4}/\d{2}/\d{2}$")
    gregorian_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    @lru_cache(maxsize=2048)
    def parse_date(date_str):
        """Parse Jalali (e.g., 1404/03/22) or Gregorian (e.g., 2025-06-02) date strings"""
        try:
            if jalali_re.match(date_str):
                jalali_date = jdatetime.datetime.strptime(date_str, "%Y/%m/%d")
                return jalali_date.togregorian(), date_str
            elif gregorian_re.match(date_str):
                gregorian_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                jalali_label = jdatetime.date.fromgregorian(date=gregorian_date.date()).strftime("%Y/%m/%d")
                return gregorian_date, jalali_label
            else:
                raise ValueError(f"فرمت تاریخ ناشناخته: {date_str}")
        except Exception as e:
            raise ValueError(f"خطا در تبدیل تاریخ '{date_str}': {e}")

    # Build data list
    data = []
    for task in tasks:
        try:
            start_gregorian, start_label = parse_date(task.start_date)
            finish_gregorian, finish_label = parse_date(task.due_date)

            data.append({
                'Task': task.title,
                'Start': start_gregorian,
                'Finish': finish_gregorian,
                'StartLabel': start_label,
                'FinishLabel': finish_label
            })
        except Exception as e:
            flash(f"خطا در پردازش تاریخ برای وظیفه '{task.title}': {e}", "danger")
            continue

    if not data:
        flash("هیچ وظیفه‌ای با تاریخ مناسب برای نمودار گانت وجود ندارد", "warning")
        return redirect(url_for('kanban.project_kanban', project_id=project_id))

    # Create DataFrame
    df = pd.DataFrame(data)

    # Generate Plotly Gantt chart
    fig = px.timeline(
        df,
        x_start="Start",
        x_end="Finish",
        y="Task",
        custom_data=[df['StartLabel'], df['FinishLabel']],
        title="نمودار زمانی فازهای پروژه"
    )

    fig.update_traces(
        hovertemplate="<b>%{y}</b><br>از: %{customdata[0]}<br>تا: %{customdata[1]}<extra></extra>"
    )

    fig.update_layout(
        font=dict(family="Vazir, sans-serif", size=14),
        title=dict(text="نمودار زمانی فازهای پروژه", x=0.5, xanchor='center'),
        yaxis=dict(autorange="reversed")
    )

    # Render HTML in-memory
    from io import StringIO
    html_buffer = StringIO()
    fig.write_html(html_buffer, include_plotlyjs='cdn')
    html = html_buffer.getvalue()

    # Inject RTL and font styles
        # <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
        # <script src="https://cdn.jsdelivr.net/npm/jalaali-js@1.1.0/dist/jalaali.min.js"></script>
    html = html.replace("<head>", """
    <head>
        <style>
            body { direction: rtl; font-family: Vazir, sans-serif !important; }
            .grant-container{
                display: flex;
                flex-direction: column;
            }
            .gantt-nav {
                width: 100%;
                height:50px;
                float: left;
                display: flex;
                flex-direction: row;
                padding:5px;
                justify-content: flex-end;
            }
            .gantt-nav a {
                background-color: #007bff;
                color: white;
                padding: 10px 20px;
                text-decoration: none;
                border-radius: 8px;
                font-size: 16px;
            }
            .gantt-nav a:hover {
                background-color: #0056b3;
            }
        </style>
        <link href="https://cdn.jsdelivr.net/gh/rastikerdar/vazir-font@v30.1.0/dist/font-face.css" rel="stylesheet" type="text/css" />
        <script>
        (function () {
            var script1 = document.createElement('script');
            script1.src = 'https://code.jquery.com/jquery-3.6.0.min.js';
            script1.onload = function () {
                var script2 = document.createElement('script');
                script2.src = 'https://unpkg.com/jalaali-js/dist/jalaali.min.js';
                script2.onload = function () {
                    setTimeout(function () {
                        const monthMap = {
                            Jan: 1, Feb: 2, Mar: 3, Apr: 4, May: 5, Jun: 6,
                            Jul: 7, Aug: 8, Sep: 9, Oct: 10, Nov: 11, Dec: 12
                        };
                        $('g.xtick text').each(function () {
                            let $el = $(this);
                            let text = $el.text().replace(/\\n/g, ' ').trim();
                            text = text.replace('2025', '').trim();

                            let parts = text.split(' ');
                            if (parts.length < 2) return;

                            let monthStr = parts[0];
                            let day = parseInt(parts[1]);
                            let year = parts[2] ? parseInt(parts[2]) : 2025;

                            let month = monthMap[monthStr];
                            if (!month || !day || !year) return;

                            const j = jalaali.toJalaali(year, month, day);
                            let jalaliDate = `${j.jy}/${String(j.jm).padStart(2, '0')}/${String(j.jd).padStart(2, '0')}`;
                            $el.text(jalaliDate);
                            $el.attr('data-jalali', jalaliDate);
                        });
                        $("*").filter(function() {
                            return $(this).text().trim() === "Task";
                        }).each(function() {
                            $(this).text('');
                        });                        
                    }, 500);
                };
                script2.onerror = function () {
                    console.error("❌ Failed to load Jalaali (script2)");
                };
                document.head.appendChild(script2);
            };
            script1.onerror = function () {
                console.error("❌ Failed to load jQuery (script1)");
            };
            document.head.appendChild(script1);
        })();


        </script>
    """)

    html = html.replace("<body>", f"""
    <body>
        <div class="grant-container">
        <div class="gantt-nav">
            <a href="{url_for('kanban.project_kanban', project_id=project_id)}">بازگشت به پروژه</a>
        </div>
    """)
    # DO NOT include jalaali again before </body>
    html = html.replace("</body>", "</div></body>")
    return Response(html, mimetype='text/html')



@kanban_bp.route('/project/<int:project_id>/column/<int:column_id>/delete', methods=['POST'])
def delete_column(project_id, column_id):
    project = Project.query.get_or_404(project_id)
    user = g.current_user
    column = KanbanColumn.query.get_or_404(column_id)

    if project.creator_id != user.id or column.project_id != project.id:
        flash("دسترسی غیرمجاز", "danger")
        return redirect(url_for('kanban.kanban_view', project_id=project_id))

    tasks = Task.query.filter_by(column_id=column.id).all()
    if tasks:
        flash("نمی‌توان ستونی که وظیفه دارد حذف کرد", "warning")
        return redirect(url_for('kanban.project_kanban', project_id=project_id))

    db.session.delete(column)
    db.session.commit()
    flash("ستون حذف شد", "success")
    return redirect(url_for('kanban.project_kanban', project_id=project_id))

@kanban_bp.route('/project/<int:project_id>/column/<int:column_id>/edit', methods=['GET', 'POST'])
def edit_column(project_id, column_id):
    project = Project.query.get_or_404(project_id)
    user = g.current_user
    column = KanbanColumn.query.get_or_404(column_id)

    # Check access permission
    if project.creator_id != user.id or column.project_id != project.id:
        flash("دسترسی غیرمجاز", "danger")
        return redirect(url_for('kanban.kanban_view', project_id=project_id))

    if request.method == 'POST':
        # Handle form submission
        column.title = request.form['title']
        column.order = int(request.form['order'])
        db.session.commit()

        flash("ویرایش ستون انجام شد", "success")
        return redirect(url_for('kanban.project_kanban', project_id=project_id))

    # GET: Render the edit form
    return render_template('edit_column.html', project=project, column=column)


@kanban_bp.route('/project/<int:project_id>/column/new', methods=['POST'])
def add_column(project_id):
    project = Project.query.get_or_404(project_id)
    user = g.current_user

    if project.creator_id != user.id:
        flash("دسترسی غیرمجاز", "danger")
        return redirect(url_for('kanban.kanban_view', project_id=project_id))

    title = request.form['title']
    max_order = db.session.query(db.func.max(KanbanColumn.order)).filter_by(project_id=project_id).scalar() or 0
    new_column = KanbanColumn(project_id=project_id, title=title, order=max_order + 1)
    db.session.add(new_column)
    db.session.commit()

    flash("ستون جدید افزوده شد", "success")
    return redirect(url_for('kanban.project_kanban', project_id=project_id))

@kanban_bp.route('/project/<int:project_id>/edit', methods=['GET', 'POST'])
def edit_project(project_id):
    project = Project.query.get_or_404(project_id)
    user = g.current_user
    if project.creator_id != user.id:
        flash("Unauthorized")
        return redirect(url_for('kanban.project_list'))

    if request.method == 'POST':
        project.title = request.form['title']
        project.description = request.form['description']
        project.start_date = request.form['start_date']
        project.end_date = request.form['end_date']
        f = request.files['attachment']
        if f:
            filename = secure_filename(f.filename)
            f.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            project.attachment = filename
        db.session.commit()
        return redirect(url_for('kanban.project_list'))

    return render_template('project_form.html', project=project)

@kanban_bp.route('/project/<int:project_id>/delete')
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    user = g.current_user
    if project.creator_id == user.id:
        db.session.delete(project)
        db.session.commit()
    return redirect(url_for('kanban.project_list'))

# ###################################
# ###################################
# ###################################
@kanban_bp.route('/project/<int:project_id>/task/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_task(project_id, task_id):
    project = Project.query.get_or_404(project_id)
    task = Task.query.get_or_404(task_id)

    # Check permissions
    column_user_ids = [u.id for u in task.column.users]
    task_owner_ids = [u.id for u in task.assigned_users]
    if current_user.id not in (task_owner_ids + column_user_ids):
        abort(403)

    # --- Form initialization
    if request.method == 'POST':
        task_form = TaskEditForm()
    else:
        task_form = TaskEditForm(obj=task)
    report_form = ReportForm()

    # Choices for columns
    task_form.column_id.choices = [(col.id, col.title) for col in project.columns]

    # --- Handle task form submission
   
    logger.info(request.method)
    logger.info("Request method: %s", request.method)
    logger.info("Form errors: %s", task_form.errors)
    logger.info("Form data: %s", task_form.data)
    logger.info("CSRF token: %s", task_form.csrf_token.data)
    if 'submit_task' in request.form and task_form.validate_on_submit():
        logger.info('i"m inside')
        updated = False

        if task_form.column_id.data and task.column_id != task_form.column_id.data:
            task.column_id = task_form.column_id.data
            flash("ستون وظیفه بروزرسانی شد", "success")
            updated = True

        logger.info("Form title: %s", task_form.title.data)
        if task_form.title.data and task.title != task_form.title.data:
            task.title = task_form.title.data
            flash("عنوان وظیفه بروزرسانی شد", "success")
            updated = True

        logger.info("Form title: %s", task_form.start_date.data)
        if task_form.start_date.data and task.start_date != task_form.start_date.data:
            task.start_date = task_form.start_date.data
            flash("تاریخ آغاز بروزرسانی شد", "success")
            updated = True
        if task_form.due_date.data and task.due_date != task_form.due_date.data:
            task.due_date = task_form.due_date.data
            flash("تاریخ پایان بروزرسانی شد", "success")
            updated = True

        if updated:
            db.session.commit()
            return redirect(url_for('kanban.edit_task', project_id=project_id, task_id=task.id))
        else:
            flash("تغییری اعمال نشد", "info")
    # --- Handle report form
    elif 'submit_report' in request.form and report_form.validate_on_submit():
        new_report = Report(
            task_id=task.id,
            user_id=current_user.id,
            text=report_form.text.data,
            created_at=datetime.utcnow()
        )
        db.session.add(new_report)
        db.session.commit()
        flash("گزارش اضافه شد", "success")
        return redirect(url_for('kanban.edit_task', project_id=project_id, task_id=task.id))

    reports = Report.query.filter_by(task_id=task.id).order_by(Report.created_at.desc()).all()

    return render_template(
        "edit_task.html",
        project=project,
        task=task,
        form=task_form,
        report_form=report_form,
        reports=reports
    )


@kanban_bp.route('/project/<int:project_id>/report/<int:report_id>/delete', methods=['POST'])
@login_required
def delete_report(project_id, report_id):
    report = Report.query.get_or_404(report_id)
    if report.user_id != current_user.id:
        abort(403)
    db.session.delete(report)
    db.session.commit()
    flash("گزارش حذف شد", "success")
    return redirect(request.referrer or url_for('kanban.project_kanban', project_id=project_id))


@kanban_bp.route('/project/<int:project_id>/tasks/new', methods=['GET', 'POST'])
@login_required
def create_task(project_id):
    project = Project.query.get_or_404(project_id)
    if current_user.id not in [project.owner_id, project.creator_id]:
        abort(403)

    columns = KanbanColumn.query.filter_by(project_id=project.id).order_by(KanbanColumn.order).all()
    if not columns:
        flash("No column found to assign task to.", "error")
        return redirect(url_for('kanban.project_kanban', project_id=project_id))

    form = TaskForm()
    form.assignee_ids.choices = [(u.id, u.name) for u in User.query.order_by(User.name).all()]
    form.column_id.choices = [(col.id, col.title) for col in columns]

    if request.method == 'POST':
        # Get dates from hidden fields
        start_date_str = request.form.get('start_date')
        due_date_str = request.form.get('due_date')

        start_date = convert_jalali_to_gregorian(start_date_str) if start_date_str else None
        due_date = convert_jalali_to_gregorian(due_date_str) if due_date_str else None

        print("Start Date (Raw):", request.form.get("start_date"))
        print("Due Date (Raw):", request.form.get("due_date"))

        if not form.title.data:
            flash("عنوان نمی‌تواند خالی باشد", "danger")
            return redirect(request.url)

        if start_date is None or due_date is None:
            flash("فرمت تاریخ نامعتبر است", "danger")
            return redirect(request.url)

        selected_user_ids = list(set(form.assignee_ids.data or []))
        selected_users = User.query.filter(User.id.in_(selected_user_ids)).all()

        task = Task(
            title=form.title.data,
            description=form.description.data,
            column_id=form.column_id.data,
            due_date=due_date,
            start_date=start_date,
            project_id=project.id,
            assigned_users=selected_users
        )

        db.session.add(task)
        db.session.commit()
        flash("وظیفه با موفقیت ایجاد شد.", "success")
        return redirect(url_for('kanban.project_kanban', project_id=project.id))

    return render_template("task_form.html", project=project, form=form)

@kanban_bp.route('/project/<int:project_id>/kanban', methods=['GET', 'POST'])
@login_required
def project_kanban(project_id):
    project = Project.query.get_or_404(project_id)

    columns = KanbanColumn.query.filter_by(project_id=project_id).all()
    tasks = {col.id: Task.query.filter_by(column_id=col.id).all() for col in columns}

    if current_user.id not in [project.owner_id, project.creator_id]:
        flash("Only the project owner or creator can add tasks.", "danger")
        return redirect(url_for('dashboard'))

    form = TaskForm()
    form.assignee_ids.choices = [(u.id, u.name) for u in project.members]
    form.column_id.choices = [(col.id, col.title) for col in columns]

    if form.validate_on_submit():
        new_task = Task(
            title=form.title.data,
            description=form.description.data,
            column_id=form.column_id.data,
            due_date=form.due_date.data,
            project_id=project.id
        )

        selected_user_ids = list(set(form.assignee_ids.data or []))  # ensure uniqueness
        selected_users = User.query.filter(User.id.in_(selected_user_ids)).all()
        new_task.assigned_users.extend(selected_users)  # ORM handles association table

        db.session.add(new_task)
        db.session.commit()

        flash("Task created successfully.", "success")
        return redirect(url_for('kanban.project_kanban', project_id=project_id))

    return render_template('kanban_board.html', project=project, columns=columns, form=form, tasks=tasks)
