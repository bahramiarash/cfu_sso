"""
بررسی اینکه چه اطلاعاتی از SSO دریافت می‌شود و چه اطلاعاتی در دیتابیس ذخیره می‌شود
Check what data is received from SSO and what is stored in database
"""
import os
import sys

# Add the app directory to the path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

def analyze_sso_data_storage():
    """تحلیل اینکه چه اطلاعاتی از SSO دریافت و ذخیره می‌شود"""
    
    print("=" * 100)
    print("📊 تحلیل ذخیره‌سازی اطلاعات SSO")
    print("=" * 100)
    print()
    
    # بررسی کد app.py
    app_file = os.path.join(BASE_DIR, 'app.py')
    if os.path.exists(app_file):
        with open(app_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # پیدا کردن بخش authorized
        if 'def authorized():' in content:
            print("✅ تابع authorized() یافت شد")
            print()
            
            # بررسی اینکه چه اطلاعاتی از SSO دریافت می‌شود
            print("📥 اطلاعات دریافت شده از SSO (از userinfo):")
            print("   - username (برای sso_id)")
            print("   - fullname (برای name)")
            print("   - usertype (برای access_level)")
            print("   - email (در session ذخیره می‌شود اما در دیتابیس ذخیره نمی‌شود)")
            print("   - firstname, lastname (در session ذخیره می‌شود)")
            print("   - national_id (در session ذخیره می‌شود)")
            print("   - province_code (در session ذخیره می‌شود اما در دیتابیس ذخیره نمی‌شود)")
            print("   - university_code (در session ذخیره می‌شود اما در دیتابیس ذخیره نمی‌شود)")
            print("   - faculty_code (در session ذخیره می‌شود اما در دیتابیس ذخیره نمی‌شود)")
            print()
            
            # بررسی اینکه چه اطلاعاتی در دیتابیس ذخیره می‌شود
            print("💾 اطلاعات ذخیره شده در جدول users:")
            print("   ✅ sso_id (از username)")
            print("   ✅ name (از fullname)")
            print("   ❌ email (ذخیره نمی‌شود)")
            print("   ❌ province_code (ذخیره نمی‌شود)")
            print("   ❌ university_code (ذخیره نمی‌شود)")
            print("   ❌ faculty_code (ذخیره نمی‌شود)")
            print()
            
            # بررسی فیلدهای موجود در مدل User
            print("📋 فیلدهای موجود در مدل User (models.py):")
            print("   ✅ id (Primary Key)")
            print("   ✅ name (NOT NULL)")
            print("   ✅ email (UNIQUE, nullable)")
            print("   ✅ sso_id (NOT NULL)")
            print("   ✅ province_code (nullable)")
            print("   ✅ university_code (nullable)")
            print("   ✅ faculty_code (nullable)")
            print()
            
            print("⚠️  مشکل:")
            print("   - فیلدهای email, province_code, university_code, faculty_code در مدل وجود دارند")
            print("   - اما در کد authorized() فقط sso_id و name ذخیره می‌شوند")
            print("   - بقیه اطلاعات فقط در session نگه داشته می‌شوند و با logout از بین می‌روند")
            print()
            
            print("💡 پیشنهاد:")
            print("   باید کد authorized() را به‌روزرسانی کنیم تا تمام اطلاعات از SSO را در دیتابیس ذخیره کند")
            print()
    
    # بررسی کد context.py
    context_file = os.path.join(BASE_DIR, 'dashboards', 'context.py')
    if os.path.exists(context_file):
        print("📂 بررسی dashboards/context.py:")
        print("   - این فایل از session برای خواندن province_code, university_code, faculty_code استفاده می‌کند")
        print("   - اگر این اطلاعات در دیتابیس ذخیره شوند، می‌توان از دیتابیس خواند")
        print()
    
    print("=" * 100)
    print("📝 خلاصه:")
    print("=" * 100)
    print("❌ خیر، تمام اطلاعات از SSO دریافت می‌شود اما فقط sso_id و name در جدول users ذخیره می‌شود.")
    print("   بقیه اطلاعات (email, province_code, university_code, faculty_code) فقط در session نگه داشته می‌شوند.")
    print()
    print("🔧 برای ذخیره تمام اطلاعات، باید کد authorized() را به‌روزرسانی کنیم.")
    print("=" * 100)

if __name__ == "__main__":
    analyze_sso_data_storage()

