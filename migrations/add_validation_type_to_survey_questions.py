"""
Migration script to add validation_type column to survey_questions table
Run this script once to update the database schema
"""
import sqlite3
import os

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'app', 'access_control.db')

def migrate():
    """Add validation_type column to survey_questions table"""
    print("Starting migration: Add validation_type to survey_questions...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(survey_questions)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Add validation_type if not exists
        if 'validation_type' not in columns:
            print("Adding validation_type column...")
            cursor.execute("ALTER TABLE survey_questions ADD COLUMN validation_type VARCHAR(20)")
            print("[OK] validation_type column added")
        else:
            print("[SKIP] validation_type column already exists")
        
        conn.commit()
        print("\n[SUCCESS] Migration completed successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()

