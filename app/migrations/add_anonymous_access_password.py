"""
Migration: Add anonymous_access_password field to surveys table
"""
import sqlite3
import os
import sys

def migrate():
    """Add anonymous_access_password column to surveys table"""
    # Get the path to survey.db
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, '..', 'survey.db')
    
    # Try alternative paths
    if not os.path.exists(db_path):
        db_path = os.path.join(script_dir, '..', '..', 'survey.db')
    if not os.path.exists(db_path):
        db_path = os.path.join(os.getcwd(), 'survey.db')
    if not os.path.exists(db_path):
        db_path = os.path.join(os.getcwd(), 'app', 'survey.db')
    if not os.path.exists(db_path):
        # Try to find survey.db in the project root
        project_root = os.path.dirname(os.path.dirname(script_dir))
        db_path = os.path.join(project_root, 'survey.db')
    
    if not os.path.exists(db_path):
        print(f"Error: Database not found. Tried paths:")
        print(f"  - {os.path.join(script_dir, '..', 'survey.db')}")
        print(f"  - {os.path.join(script_dir, '..', '..', 'survey.db')}")
        print(f"  - {os.path.join(os.getcwd(), 'survey.db')}")
        print(f"  - {os.path.join(os.getcwd(), 'app', 'survey.db')}")
        sys.exit(1)
    
    print(f"Connecting to database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(surveys)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'anonymous_access_password' in columns:
            print("Column 'anonymous_access_password' already exists. Skipping migration.")
        else:
            # Add the column
            cursor.execute("""
                ALTER TABLE surveys 
                ADD COLUMN anonymous_access_password TEXT
            """)
            conn.commit()
            print("Successfully added 'anonymous_access_password' column to surveys table.")
    except Exception as e:
        conn.rollback()
        print(f"Error during migration: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()

