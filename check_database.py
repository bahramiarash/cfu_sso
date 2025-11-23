"""
Check database tables and users
"""
import sqlite3
import os

BASE_DIR = os.path.join(os.path.dirname(__file__), 'app')
DB_PATH = os.path.join(BASE_DIR, 'access_control.db')

def check_database():
    """Check database tables and users"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("=" * 60)
    print("Database Check")
    print("=" * 60)
    
    # Check tables
    print("\n1. Checking tables...")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()
    print(f"   Found {len(tables)} tables:")
    for table in tables:
        print(f"   - {table[0]}")
    
    # Check admin tables
    admin_tables = ['dashboard_access', 'access_logs', 'data_syncs', 'dashboard_configs']
    print("\n2. Checking admin panel tables...")
    for table in admin_tables:
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
        exists = cursor.fetchone()
        if exists:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"   [OK] {table}: {count} records")
        else:
            print(f"   [MISSING] {table}")
    
    # Check users
    print("\n3. Checking users...")
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    print(f"   Total users: {user_count}")
    
    cursor.execute("SELECT id, sso_id, name FROM users LIMIT 10")
    users = cursor.fetchall()
    print(f"   Sample users:")
    for user in users:
        print(f"   - ID: {user[0]}, SSO: {user[1]}, Name: {user[2]}")
    
    # Check access levels
    print("\n4. Checking access levels...")
    cursor.execute("SELECT COUNT(*) FROM access_levels")
    access_count = cursor.fetchone()[0]
    print(f"   Total access levels: {access_count}")
    
    cursor.execute("""
        SELECT u.sso_id, u.name, a.level 
        FROM users u 
        JOIN access_levels a ON u.id = a.user_id 
        ORDER BY u.sso_id
    """)
    access_levels = cursor.fetchall()
    print(f"   User access levels:")
    for sso_id, name, level in access_levels:
        print(f"   - {sso_id} ({name}): {level}")
    
    # Check bahrami
    print("\n5. Checking user 'bahrami'...")
    cursor.execute("SELECT id, sso_id, name FROM users WHERE sso_id = 'bahrami'")
    bahrami = cursor.fetchone()
    if bahrami:
        user_id = bahrami[0]
        print(f"   [OK] User found: {bahrami[2]} (ID: {user_id})")
        
        cursor.execute("SELECT level FROM access_levels WHERE user_id = ?", (user_id,))
        levels = cursor.fetchall()
        if levels:
            print(f"   Access levels: {[l[0] for l in levels]}")
        else:
            print(f"   [WARNING] No access levels found!")
    else:
        print(f"   [NOT FOUND] User 'bahrami' not found in database")
    
    conn.close()
    print("\n" + "=" * 60)

if __name__ == '__main__':
    check_database()

