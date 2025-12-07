"""
Migration: Add API credentials fields to data_syncs table
"""
import sqlite3
import os

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'access_control.db')

def migrate():
    """Add API credentials fields to data_syncs table"""
    print("Starting migration: Add API credentials to data_syncs...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(data_syncs)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Add api_username if not exists
        if 'api_username' not in columns:
            cursor.execute("ALTER TABLE data_syncs ADD COLUMN api_username VARCHAR(200)")
            print("[OK] Added api_username column")
        else:
            print("[SKIP] api_username column already exists")
        
        # Add api_password if not exists (will be encrypted in production)
        if 'api_password' not in columns:
            cursor.execute("ALTER TABLE data_syncs ADD COLUMN api_password VARCHAR(500)")
            print("[OK] Added api_password column")
        else:
            print("[SKIP] api_password column already exists")
        
        # Add api_base_url if not exists
        if 'api_base_url' not in columns:
            cursor.execute("ALTER TABLE data_syncs ADD COLUMN api_base_url VARCHAR(500)")
            print("[OK] Added api_base_url column")
        else:
            print("[SKIP] api_base_url column already exists")
        
        # Update default values for faculty sync
        cursor.execute("""
            UPDATE data_syncs 
            SET api_base_url = 'https://api.cfu.ac.ir',
                api_username = 'khodarahmi',
                api_password = '9909177',
                api_endpoint = 'https://api.cfu.ac.ir/API/Golestan/Faculty',
                api_method = 'POST'
            WHERE data_source = 'faculty' 
            AND (api_base_url IS NULL OR api_base_url = '')
        """)
        
        # Update default values for students sync
        cursor.execute("""
            UPDATE data_syncs 
            SET api_base_url = 'https://api.cfu.ac.ir',
                api_username = 'khodarahmi',
                api_password = '9909177',
                api_endpoint = 'https://api.cfu.ac.ir/API/Golestan/Students_2',
                api_method = 'POST'
            WHERE data_source = 'students' 
            AND (api_base_url IS NULL OR api_base_url = '')
        """)
        
        conn.commit()
        print("\n[SUCCESS] Migration completed successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    migrate()


