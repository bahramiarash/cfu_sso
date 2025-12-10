"""
اسکریپت نمایش اطلاعات جدول کاربران
Script to display user table information
"""
import os
import sys
import sqlite3
from pathlib import Path

# Add the app directory to the path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

def display_users():
    """نمایش اطلاعات تمام کاربران"""
    db_file = os.path.join(BASE_DIR, 'access_control.db')
    
    if not os.path.exists(db_file):
        print(f"❌ فایل دیتابیس یافت نشد: {db_file}")
        return
    
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # دریافت اطلاعات کاربران
    cursor.execute("""
        SELECT 
            u.id,
            u.name,
            u.email,
            u.sso_id,
            u.province_code,
            u.university_code,
            u.faculty_code,
            GROUP_CONCAT(al.level, ', ') as access_levels
        FROM users u
        LEFT JOIN access_levels al ON u.id = al.user_id
        GROUP BY u.id
        ORDER BY u.id
    """)
    
    users = cursor.fetchall()
    
    if not users:
        print("⚠️ هیچ کاربری در دیتابیس یافت نشد.")
        conn.close()
        return
    
    print("=" * 100)
    print(f"📊 اطلاعات جدول کاربران - تعداد کل: {len(users)}")
    print("=" * 100)
    print()
    
    # نمایش اطلاعات هر کاربر
    for idx, user in enumerate(users, 1):
        print(f"👤 کاربر #{idx} (ID: {user['id']})")
        print(f"   نام: {user['name']}")
        print(f"   SSO ID: {user['sso_id']}")
        print(f"   ایمیل: {user['email'] or '(خالی)'}")
        print(f"   کد استان: {user['province_code'] or '(خالی)'}")
        print(f"   کد دانشگاه: {user['university_code'] or '(خالی)'}")
        print(f"   کد دانشکده: {user['faculty_code'] or '(خالی)'}")
        print(f"   سطوح دسترسی: {user['access_levels'] or '(بدون دسترسی)'}")
        print("-" * 100)
    
    # آمار کلی
    print()
    print("=" * 100)
    print("📈 آمار کلی:")
    print("=" * 100)
    
    # تعداد کاربران با ایمیل
    cursor.execute("SELECT COUNT(*) FROM users WHERE email IS NOT NULL AND email != ''")
    users_with_email = cursor.fetchone()[0]
    
    # تعداد کاربران با کد استان
    cursor.execute("SELECT COUNT(*) FROM users WHERE province_code IS NOT NULL")
    users_with_province = cursor.fetchone()[0]
    
    # تعداد کاربران با کد دانشگاه
    cursor.execute("SELECT COUNT(*) FROM users WHERE university_code IS NOT NULL")
    users_with_university = cursor.fetchone()[0]
    
    # تعداد کاربران با کد دانشکده
    cursor.execute("SELECT COUNT(*) FROM users WHERE faculty_code IS NOT NULL")
    users_with_faculty = cursor.fetchone()[0]
    
    # تعداد کاربران با دسترسی
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM access_levels")
    users_with_access = cursor.fetchone()[0]
    
    # توزیع سطوح دسترسی
    cursor.execute("""
        SELECT level, COUNT(*) as count 
        FROM access_levels 
        GROUP BY level 
        ORDER BY count DESC
    """)
    access_levels = cursor.fetchall()
    
    print(f"   تعداد کل کاربران: {len(users)}")
    print(f"   کاربران با ایمیل: {users_with_email}")
    print(f"   کاربران با کد استان: {users_with_province}")
    print(f"   کاربران با کد دانشگاه: {users_with_university}")
    print(f"   کاربران با کد دانشکده: {users_with_faculty}")
    print(f"   کاربران با دسترسی: {users_with_access}")
    print()
    print("   توزیع سطوح دسترسی:")
    for level in access_levels:
        print(f"      - {level['level']}: {level['count']} کاربر")
    
    conn.close()
    print()
    print("=" * 100)

if __name__ == "__main__":
    display_users()

