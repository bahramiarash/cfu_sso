# app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_session import Session
from flask_login import LoginManager

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__, template_folder="templates")
    
    # Load config
    app.config.from_object("config.Config")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///access_control.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SESSION_TYPE"] = "filesystem"
    app.config["UPLOAD_FOLDER"] = "static/uploads"
    app.secret_key = "your-secret-key"

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    Session(app)
    login_manager.init_app(app)

    # Register blueprints
    from .dashboard import dashboard_bp
    from .students_dashboard import students_bp
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(students_bp)

    return app
