"""
تحلیل دقیق فیلدهای دریافتی از SSO و مقایسه با فیلدهای ذخیره شده
"""
import json

# داده‌های دریافتی از SSO (از لاگ)
sso_data = {
    'sub': '353',
    'email': 'Bahrami@cfu.ac.ir',
    'email_verified': 0,
    'name': 'bahrami',
    'preferred_username': 'bahrami',
    'picture': 'http://sso.nit.ac.ir/sites/all/modules/iust/images/anonymous.png',
    'id': 'bahrami',
    'username': 'bahrami',
    'firstname': 'آرش',
    'lastname': 'بهرامی',
    'enfirstname': 'Arash',
    'enlastname': 'Bahrami',
    'gender': '0',
    'statename': 'شاغل',
    'usertype': 'staff',
    'usertypename': 'کارمند',
    'department': 'اداره کل هوشمندسازي و امنيت فضاي محازي',
    'departmentcode': '5009',
    'phone': '09123880167',
    'sid': None
}

# فیلدهای موجود در مدل User
user_model_fields = [
    'id',           # Primary Key
    'name',          # NOT NULL
    'email',         # UNIQUE, nullable
    'sso_id',        # NOT NULL
    'province_code', # nullable
    'university_code', # nullable
    'faculty_code'   # nullable
]

print("=" * 100)
print("📊 تحلیل کامل فیلدهای SSO و ذخیره‌سازی")
print("=" * 100)
print()

print("📥 فیلدهای دریافتی از SSO:")
for key, value in sso_data.items():
    print(f"   - {key}: {value}")
print()

print("💾 فیلدهای موجود در مدل User:")
for field in user_model_fields:
    print(f"   - {field}")
print()

print("=" * 100)
print("✅ فیلدهایی که ذخیره می‌شوند:")
print("=" * 100)
stored_fields = {
    'sso_id': 'username',
    'name': 'firstname + lastname (یا fullname اگر موجود باشد)',
    'email': 'email',
    'province_code': 'province_code یا provinceCode',
    'university_code': 'university_code یا universityCode',
    'faculty_code': 'faculty_code یا facultyCode یا code_markaz'
}
for field, source in stored_fields.items():
    print(f"   ✅ {field} ← {source}")
print()

print("=" * 100)
print("❌ فیلدهایی که ذخیره نمی‌شوند:")
print("=" * 100)
not_stored = [
    ('sub', 'شناسه یکتا در SSO'),
    ('email_verified', 'وضعیت تایید ایمیل'),
    ('preferred_username', 'نام کاربری ترجیحی'),
    ('picture', 'آدرس تصویر پروفایل'),
    ('id', 'شناسه SSO (مشابه username)'),
    ('firstname', 'نام (فقط برای ساخت name استفاده می‌شود)'),
    ('lastname', 'نام خانوادگی (فقط برای ساخت name استفاده می‌شود)'),
    ('enfirstname', 'نام انگلیسی'),
    ('enlastname', 'نام خانوادگی انگلیسی'),
    ('gender', 'جنسیت'),
    ('statename', 'وضعیت (شاغل/بازنشسته)'),
    ('usertype', 'نوع کاربر (staff/student)'),
    ('usertypename', 'نام نوع کاربر'),
    ('department', 'نام دپارتمان/اداره'),
    ('departmentcode', 'کد دپارتمان'),
    ('phone', 'شماره تلفن'),
    ('sid', 'شناسه دانشجویی')
]
for field, desc in not_stored:
    print(f"   ❌ {field}: {desc}")
print()

print("=" * 100)
print("⚠️  مشکلات شناسایی شده:")
print("=" * 100)
print("1. در کد از 'fullname' استفاده می‌شود اما در userinfo از SSO، fullname وجود ندارد!")
print("   باید از firstname + lastname استفاده شود.")
print()
print("2. اطلاعات مهمی مثل department, departmentcode, phone ذخیره نمی‌شوند.")
print()
print("3. firstname و lastname به صورت جداگانه ذخیره نمی‌شوند (فقط name ذخیره می‌شود).")
print()
print("4. province_code, university_code, faculty_code در userinfo از SSO وجود ندارند!")
print("   ممکن است در departmentcode یا فیلدهای دیگر باشند.")
print()

print("=" * 100)
print("💡 پیشنهادات:")
print("=" * 100)
print("1. اضافه کردن فیلدهای جدید به مدل User:")
print("   - firstname, lastname")
print("   - phone")
print("   - department, departmentcode")
print("   - usertype")
print("   - gender")
print("   - picture")
print()
print("2. اصلاح کد authorized() برای:")
print("   - استفاده از firstname + lastname به جای fullname")
print("   - ذخیره تمام فیلدهای جدید")
print("   - استخراج province_code, university_code, faculty_code از departmentcode یا فیلدهای دیگر")
print("=" * 100)

