from sqlalchemy.orm import relationship
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import event, Column, Integer, ForeignKey
from sqlalchemy.orm import Session
import sqlite3
import os
from flask_login import UserMixin
from datetime import datetime
from jdatetime import datetime as jdatetime
from extensions import db

# db = SQLAlchemy()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))  # Directory where this script lives
DB_PATH = f"sqlite:///{os.path.join(BASE_DIR, 'access_control.db')}"
DB_PATH2 = f"sqlite:///{os.path.join(BASE_DIR, '/fetch_data/faculty_data.db')}"

def convert_jalali_to_gregorian(shamsi_str: str):
    """Convert a Jalali datetime string to Gregorian datetime."""
    return jdatetime.strptime(shamsi_str, "%Y-%m-%d %H:%M").togregorian()
    
# Define association table first, before models that use it
project_members = db.Table(
    'project_members',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('project_id', db.Integer, db.ForeignKey('projects.id'), primary_key=True)
)

kanban_column_users = db.Table(
    'kanban_column_users',
    db.metadata,
    db.Column('column_id', db.Integer, db.ForeignKey('kanban_columns.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True)
)

# task_assigned_users = db.Table(
#     'task_assigned_users',
#     db.Column('task_id', db.Integer, db.ForeignKey('tasks.id')),
#     db.Column('user_id', db.Integer, db.ForeignKey('users.id'))
# )


def get_db_connection():
    db_file = f"{os.path.join(BASE_DIR, 'access_control.db')}"
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row  # Optional: allows accessing columns by name
    return conn

def get_db_connection2():
    db_file = f"{os.path.join(BASE_DIR+'/fetch_data', 'faculty_data.db')}"
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row  # Optional: allows accessing columns by name
    return conn

class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    name = Column(db.String, nullable=False)
    email = Column(db.String, unique=True)
    sso_id = Column(db.String, nullable=False)

    # Define relationship to KanbanColumn through association table
    kanban_columns = db.relationship(
        'KanbanColumn',
        secondary=kanban_column_users,
        back_populates='users'
    )

    # Projects user created, specify foreign_keys
    projects_created = db.relationship('Project', foreign_keys='Project.creator_id', back_populates='creator')

    # Projects user owns, specify foreign_keys
    projects_owned = db.relationship('Project', foreign_keys='Project.owner_id', back_populates='owner')

    # Many-to-many membership in projects
    member_projects = db.relationship('Project', secondary=project_members, back_populates='members')

    tasks_assigned = db.relationship(
        'Task',
        secondary='task_assigned_users',
        back_populates='assigned_users'
    )

    # Other relationships as before...


class Project(db.Model):
    __tablename__ = 'projects'

    # Columns
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    title = db.Column(db.String)
    description = db.Column(db.Text)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    sso_id = db.Column(db.String)
    attachment = db.Column(db.String)
    start_date = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)
    tasks = db.relationship('Task', back_populates='project')

    # Relationships with explicit foreign_keys
    creator = db.relationship('User', foreign_keys=[creator_id], back_populates='projects_created')
    owner = db.relationship('User', foreign_keys=[owner_id], back_populates='projects_owned')

    # Many-to-many with members (no change here)
    members = db.relationship('User', secondary=project_members, back_populates='member_projects')

    columns = db.relationship('KanbanColumn', back_populates='project', cascade='all, delete-orphan')




class KanbanColumn(db.Model):
    __tablename__ = 'kanban_columns'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    order = db.Column(db.Integer, nullable=False)

    # project = db.relationship("Project", backref=db.backref("kanban_columns", lazy=True))
    tasks = db.relationship(
        "Task",
        back_populates="kanban_column",
        lazy=True,
        cascade="all, delete-orphan",
    )



    # project = db.relationship('Project', backref=db.backref('columns', lazy=True))
    project = relationship("Project", back_populates="columns")

    users = db.relationship(
        'User',
        secondary=kanban_column_users,
        back_populates='kanban_columns'
    )

class Task(db.Model):
    __tablename__ = 'tasks'

    id = db.Column(db.Integer, primary_key=True)
    column_id = db.Column(db.Integer, db.ForeignKey('kanban_columns.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    due_date = db.Column(db.Text, nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'))
    project = db.relationship('Project', back_populates='tasks')
    reports = db.relationship('Report', back_populates='task', cascade='all, delete-orphan')
    start_date = db.Column(db.Text, nullable=True)  # Accept from form or fallback

    assigned_labels = db.relationship('TaskLabelAssignment', back_populates='task', cascade='all, delete-orphan')
    column = db.relationship(
        "KanbanColumn",
        back_populates="tasks",
    )
    kanban_column = db.relationship(
        "KanbanColumn",
        back_populates="tasks",
    )

    assigned_users = db.relationship(
        'User',
        secondary='task_assigned_users',
        back_populates='tasks_assigned'
    )


class AccessLevel(db.Model):
    __tablename__ = 'access_levels'

    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

# Event listener for default Kanban columns
@event.listens_for(Project, 'after_insert')
def create_default_kanban_columns(mapper, connection, target):
    default_columns = [
        {"title": "برای انجام", "order": 1},
        {"title": "در دست انجام", "order": 2},
        {"title": "انجام شده", "order": 3},
    ]
    connection.execute(
        KanbanColumn.__table__.insert(),
        [
            {
                "title": col["title"],
                "order": col["order"],
                "project_id": target.id
            }
            for col in default_columns
        ]
    )
class TaskAssignedUser(db.Model):
    __tablename__ = 'task_assigned_users'

    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)

class Report(db.Model):
    __tablename__ = 'reports'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    task = db.relationship('Task', back_populates='reports')
    user = db.relationship('User')

class Label(db.Model):
    __tablename__ = 'labels'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # e.g., وضعیت تسک
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)  # Optional: project-specific

    values = db.relationship('LabelValue', backref='label', cascade='all, delete-orphan')


class LabelValue(db.Model):
    __tablename__ = 'label_values'
    id = db.Column(db.Integer, primary_key=True)
    label_id = db.Column(db.Integer, db.ForeignKey('labels.id'), nullable=False)
    value = db.Column(db.String(100), nullable=False)  # e.g., در دست انجام

    # Optional: enforce uniqueness of value per label
    __table_args__ = (db.UniqueConstraint('label_id', 'value', name='_label_value_uc'),)

class TaskLabelAssignment(db.Model):
    __tablename__ = 'task_label_assignments'
    id = db.Column(db.Integer, primary_key=True)

    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    label_id = db.Column(db.Integer, db.ForeignKey('labels.id'), nullable=False)
    label_value_id = db.Column(db.Integer, db.ForeignKey('label_values.id'), nullable=False)

    task = db.relationship('Task', back_populates='assigned_labels')
    label = db.relationship('Label')
    label_value = db.relationship('LabelValue')

    __table_args__ = (
        db.UniqueConstraint('task_id', 'label_id', name='_task_label_uc'),  # only one value per label per task
    )