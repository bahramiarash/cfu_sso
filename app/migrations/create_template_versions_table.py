import sqlite3
import os
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'access_control.db')

def migrate():
    print("Starting template_versions migration...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("PRAGMA table_info(template_versions)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'id' in columns:
            print("[SKIP] template_versions table already exists")
            return

        cursor.execute("""
            CREATE TABLE template_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_name VARCHAR(200) NOT NULL,
                version_number INTEGER NOT NULL,
                template_content TEXT NOT NULL,
                chart_configs TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                description TEXT,
                FOREIGN KEY (created_by) REFERENCES users(id),
                UNIQUE (template_name, version_number)
            )
        """)
        print("[OK] Created template_versions table")
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_template_versions_template ON template_versions(template_name, version_number)")
        print("[OK] Created indexes for template_versions")
        
        conn.commit()
        print("\n[SUCCESS] template_versions migration completed successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()

