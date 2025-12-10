"""
Script to check which users need to be updated with SSO information
Users with "Unnamed User" as their name will be updated on their next login
"""
import sqlite3
import os
import sys

# Add parent directory to path to import models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'access_control.db')

def check_users():
    """Check which users need SSO information update"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        print("=" * 60)
        print("بررسی کاربران نیازمند به‌روزرسانی")
        print("=" * 60)
        
        # Check users with "Unnamed User" or missing firstname/lastname
        cursor.execute("""
            SELECT id, sso_id, name, firstname, lastname, email
            FROM users
            WHERE name = 'Unnamed User' 
               OR (firstname IS NULL AND lastname IS NULL)
            ORDER BY id
        """)
        
        users_needing_update = cursor.fetchall()
        
        if not users_needing_update:
            print("\n✅ همه کاربران اطلاعات SSO را دارند!")
            print("   هیچ کاربری نیاز به به‌روزرسانی ندارد.")
        else:
            print(f"\n⚠️  {len(users_needing_update)} کاربر نیاز به به‌روزرسانی دارند:")
            print("\n" + "-" * 60)
            print(f"{'ID':<5} {'SSO ID':<20} {'Name':<20} {'Firstname':<15} {'Lastname':<15}")
            print("-" * 60)
            
            for user_id, sso_id, name, firstname, lastname, email in users_needing_update:
                print(f"{user_id:<5} {sso_id:<20} {name:<20} {firstname or 'N/A':<15} {lastname or 'N/A':<15}")
            
            print("\n" + "-" * 60)
            print("\n📝 توضیحات:")
            print("   - این کاربران در ورود بعدی خود به‌طور خودکار به‌روزرسانی می‌شوند")
            print("   - اطلاعات SSO از SSO server دریافت و در دیتابیس ذخیره می‌شود")
            print("   - کاربران باید از سیستم خارج شده و دوباره وارد شوند")
        
        # Show all users summary
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE firstname IS NOT NULL AND lastname IS NOT NULL")
        users_with_sso = cursor.fetchone()[0]
        
        print("\n" + "=" * 60)
        print("خلاصه:")
        print(f"   کل کاربران: {total_users}")
        print(f"   کاربران با اطلاعات SSO: {users_with_sso}")
        print(f"   کاربران نیازمند به‌روزرسانی: {len(users_needing_update)}")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ خطا: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    check_users()

