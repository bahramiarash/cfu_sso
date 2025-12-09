"""
Migration: Create survey system tables
Creates all tables for the survey/questionnaire system
"""
import sqlite3
import os
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'access_control.db')

def migrate():
    """Create survey system tables"""
    print("Starting survey system migration...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Create survey_managers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS survey_managers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        """)
        print("[OK] Created survey_managers table")
        
        # Create surveys table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS surveys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title VARCHAR(500) NOT NULL,
                description TEXT,
                manager_id INTEGER NOT NULL,
                start_date DATETIME,
                end_date DATETIME,
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                access_type VARCHAR(20) NOT NULL DEFAULT 'public',
                max_completions_per_user INTEGER NOT NULL DEFAULT 1,
                completion_period_type VARCHAR(20) NOT NULL DEFAULT 'yearly',
                logo_path VARCHAR(500),
                welcome_message TEXT,
                welcome_button_text VARCHAR(100) DEFAULT 'شروع نظرسنجی',
                display_mode VARCHAR(20) NOT NULL DEFAULT 'multi_page',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (manager_id) REFERENCES survey_managers(id)
            )
        """)
        print("[OK] Created surveys table")
        
        # Create survey_access_groups table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS survey_access_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_id INTEGER NOT NULL,
                access_level VARCHAR(50) NOT NULL,
                province_codes TEXT,
                university_codes TEXT,
                faculty_codes TEXT,
                FOREIGN KEY (survey_id) REFERENCES surveys(id) ON DELETE CASCADE
            )
        """)
        print("[OK] Created survey_access_groups table")
        
        # Create survey_allowed_users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS survey_allowed_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_id INTEGER NOT NULL,
                national_id VARCHAR(20) NOT NULL,
                FOREIGN KEY (survey_id) REFERENCES surveys(id) ON DELETE CASCADE,
                UNIQUE(survey_id, national_id)
            )
        """)
        print("[OK] Created survey_allowed_users table")
        
        # Create survey_categories table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS survey_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_id INTEGER NOT NULL,
                title VARCHAR(500) NOT NULL,
                description TEXT,
                `order` INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (survey_id) REFERENCES surveys(id) ON DELETE CASCADE
            )
        """)
        print("[OK] Created survey_categories table")
        
        # Create survey_questions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS survey_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_id INTEGER NOT NULL,
                category_id INTEGER,
                question_type VARCHAR(50) NOT NULL,
                question_text TEXT NOT NULL,
                description TEXT,
                `order` INTEGER NOT NULL DEFAULT 0,
                is_required BOOLEAN NOT NULL DEFAULT 1,
                options TEXT,
                FOREIGN KEY (survey_id) REFERENCES surveys(id) ON DELETE CASCADE,
                FOREIGN KEY (category_id) REFERENCES survey_categories(id) ON DELETE SET NULL
            )
        """)
        print("[OK] Created survey_questions table")
        
        # Create survey_responses table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS survey_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                survey_id INTEGER NOT NULL,
                user_id INTEGER,
                national_id VARCHAR(20),
                is_completed BOOLEAN NOT NULL DEFAULT 0,
                started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME,
                ip_address VARCHAR(45),
                user_agent TEXT,
                completion_period_key VARCHAR(50),
                FOREIGN KEY (survey_id) REFERENCES surveys(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        print("[OK] Created survey_responses table")
        
        # Create survey_answer_items table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS survey_answer_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                response_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                answer_text TEXT,
                answer_value INTEGER,
                file_path VARCHAR(500),
                FOREIGN KEY (response_id) REFERENCES survey_responses(id) ON DELETE CASCADE,
                FOREIGN KEY (question_id) REFERENCES survey_questions(id) ON DELETE CASCADE,
                UNIQUE(response_id, question_id)
            )
        """)
        print("[OK] Created survey_answer_items table")
        
        # Create survey_logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS survey_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action_type VARCHAR(100) NOT NULL,
                resource_type VARCHAR(50),
                resource_id INTEGER,
                ip_address VARCHAR(45),
                user_agent TEXT,
                request_path VARCHAR(500),
                request_method VARCHAR(10),
                details TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        print("[OK] Created survey_logs table")
        
        # Create indexes for better performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_survey_managers_user ON survey_managers(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_surveys_manager ON surveys(manager_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_surveys_status ON surveys(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_surveys_dates ON surveys(start_date, end_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_survey_access_groups_survey ON survey_access_groups(survey_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_survey_allowed_users_survey ON survey_allowed_users(survey_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_survey_allowed_users_national_id ON survey_allowed_users(national_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_survey_categories_survey ON survey_categories(survey_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_survey_questions_survey ON survey_questions(survey_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_survey_questions_category ON survey_questions(category_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_survey_responses_survey ON survey_responses(survey_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_survey_responses_user ON survey_responses(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_survey_responses_national_id ON survey_responses(national_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_survey_responses_completed ON survey_responses(is_completed)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_survey_responses_period ON survey_responses(completion_period_key)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_survey_answer_items_response ON survey_answer_items(response_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_survey_answer_items_question ON survey_answer_items(question_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_survey_logs_user ON survey_logs(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_survey_logs_action ON survey_logs(action_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_survey_logs_created_at ON survey_logs(created_at)")
        print("[OK] Created indexes")
        
        conn.commit()
        print("\n[SUCCESS] Survey system migration completed successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    migrate()

