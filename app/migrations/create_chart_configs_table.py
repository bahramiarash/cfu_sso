"""
Migration script to create chart_configs table
Run this script to create the chart_configs table in the database
"""
import sqlite3
import os
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'access_control.db')

def migrate():
    print("Starting chart_configs migration...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chart_configs'")
        if cursor.fetchone():
            print("[SKIP] chart_configs table already exists")
            return

        # Create table
        cursor.execute("""
            CREATE TABLE chart_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_name VARCHAR(200) NOT NULL,
                chart_id VARCHAR(200) NOT NULL,
                title VARCHAR(500),
                display_order INTEGER NOT NULL DEFAULT 0,
                chart_type VARCHAR(50) NOT NULL DEFAULT 'line',
                show_labels BOOLEAN NOT NULL DEFAULT 1,
                show_legend BOOLEAN NOT NULL DEFAULT 1,
                allow_export BOOLEAN NOT NULL DEFAULT 1,
                chart_options TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                FOREIGN KEY (created_by) REFERENCES users(id),
                UNIQUE (template_name, chart_id)
            )
        """)
        print("[OK] Created chart_configs table")
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chart_configs_template_chart ON chart_configs(template_name, chart_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chart_configs_template ON chart_configs(template_name)")
        print("[OK] Created indexes for chart_configs")
        
        conn.commit()
        print("\n[SUCCESS] chart_configs migration completed successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()

