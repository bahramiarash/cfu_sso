"""
Migration script to add is_visible column to chart_configs table
Run this script to add the is_visible column to the existing chart_configs table
"""
import sqlite3
import os
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'access_control.db')

def migrate():
    print("Starting migration: add is_visible to chart_configs...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chart_configs'")
        if not cursor.fetchone():
            print("[SKIP] chart_configs table does not exist. Run create_chart_configs_table.py first.")
            return
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(chart_configs)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'is_visible' in columns:
            print("[SKIP] is_visible column already exists in chart_configs table")
            return
        
        # Add is_visible column
        print("[INFO] Adding is_visible column to chart_configs table...")
        cursor.execute("""
            ALTER TABLE chart_configs 
            ADD COLUMN is_visible BOOLEAN NOT NULL DEFAULT 1
        """)
        print("[OK] Added is_visible column with default value 1 (True)")
        
        # Update existing records to have is_visible = 1 (True) if needed
        # This is already handled by the DEFAULT constraint, but we'll verify
        cursor.execute("UPDATE chart_configs SET is_visible = 1 WHERE is_visible IS NULL")
        print("[OK] Updated existing records to have is_visible = 1")
        
        conn.commit()
        print("\n[SUCCESS] Migration completed successfully!")
        print("  - Added is_visible column to chart_configs table")
        print("  - Default value: 1 (True)")
        print("  - All existing charts will be visible by default")
        
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()

