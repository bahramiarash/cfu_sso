"""
Script to add admin access to a user
Usage: python add_admin_access.py <sso_id>
"""
import sys
import os
import sqlite3

# Fix encoding for Windows console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Path to database
BASE_DIR = os.path.join(os.path.dirname(__file__), 'app')
DB_PATH = os.path.join(BASE_DIR, 'access_control.db')

def add_admin_access(sso_id):
    """Add admin access to a user"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Find user
        cursor.execute("SELECT id, name, email, sso_id FROM users WHERE sso_id = ?", (sso_id,))
        user = cursor.fetchone()
        
        if not user:
            print(f"Error: User with SSO ID '{sso_id}' not found!")
            return False
        
        user_id, user_name, user_email, user_sso_id = user
        print(f"OK: User found: {user_name} (ID: {user_id})")
        
        # Check if user already has admin access
        cursor.execute("""
            SELECT id FROM access_levels 
            WHERE user_id = ? AND level = 'admin'
        """, (user_id,))
        existing_admin = cursor.fetchone()
        
        if existing_admin:
            print(f"Warning: User '{sso_id}' already has admin access!")
            return True
        
        # Add admin access
        cursor.execute("""
            INSERT INTO access_levels (level, user_id)
            VALUES (?, ?)
        """, ('admin', user_id))
        
        conn.commit()
        
        print(f"Success: Admin access added to user '{sso_id}'!")
        print(f"   Name: {user_name}")
        print(f"   SSO ID: {user_sso_id}")
        print(f"   Email: {user_email or 'N/A'}")
        
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    sso_id = 'bahrami'
    
    if len(sys.argv) > 1:
        sso_id = sys.argv[1]
    
    print(f"Adding admin access to user '{sso_id}'...")
    print("-" * 50)
    
    add_admin_access(sso_id)
