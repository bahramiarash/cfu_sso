"""
Migration script to add SSO fields to User model
Run this script once to update the database schema
"""
import sqlite3
import os

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'access_control.db')

def migrate():
    """Add SSO fields to users table"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # List of SSO fields to add
        sso_fields = [
            ('sub', 'TEXT'),
            ('email_verified', 'INTEGER'),  # SQLite doesn't have BOOLEAN, use INTEGER
            ('preferred_username', 'TEXT'),
            ('picture', 'TEXT'),
            ('firstname', 'TEXT'),
            ('lastname', 'TEXT'),
            ('enfirstname', 'TEXT'),
            ('enlastname', 'TEXT'),
            ('gender', 'TEXT'),
            ('statename', 'TEXT'),
            ('usertype', 'TEXT'),
            ('usertypename', 'TEXT'),
            ('department', 'TEXT'),
            ('departmentcode', 'TEXT'),
            ('phone', 'TEXT'),
            ('sid', 'TEXT')
        ]
        
        for field_name, field_type in sso_fields:
            if field_name not in columns:
                print(f"Adding {field_name} column...")
                cursor.execute(f"ALTER TABLE users ADD COLUMN {field_name} {field_type}")
                print(f"[OK] {field_name} added")
            else:
                print(f"[OK] {field_name} already exists")
        
        conn.commit()
        print("\n[SUCCESS] Migration completed successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    print("Starting migration to add SSO fields to users table...")
    migrate()

