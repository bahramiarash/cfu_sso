"""
Migration script to add organizational fields to User model
Run this script once to update the database schema
"""
import sqlite3
import os

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'access_control.db')

def migrate():
    """Add organizational fields to users table"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Add province_code if not exists
        if 'province_code' not in columns:
            print("Adding province_code column...")
            cursor.execute("ALTER TABLE users ADD COLUMN province_code INTEGER")
            print("[OK] province_code added")
        else:
            print("[OK] province_code already exists")
        
        # Add university_code if not exists
        if 'university_code' not in columns:
            print("Adding university_code column...")
            cursor.execute("ALTER TABLE users ADD COLUMN university_code INTEGER")
            print("[OK] university_code added")
        else:
            print("[OK] university_code already exists")
        
        # Add faculty_code if not exists
        if 'faculty_code' not in columns:
            print("Adding faculty_code column...")
            cursor.execute("ALTER TABLE users ADD COLUMN faculty_code INTEGER")
            print("[OK] faculty_code added")
        else:
            print("[OK] faculty_code already exists")
        
        conn.commit()
        print("\n[SUCCESS] Migration completed successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    print("Starting migration...")
    migrate()

