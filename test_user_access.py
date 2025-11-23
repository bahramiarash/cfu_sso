"""
اسکریپت تست دسترسی کاربران
این اسکریپت دسترسی کاربران مختلف به داشبوردها را تست می‌کند
"""
import sys
import os

# اضافه کردن مسیر app به path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app import app
from models import db, User, AccessLevel
from dashboards.registry import DashboardRegistry
from dashboards.context import UserContext

def create_test_users():
    """ایجاد کاربران تست"""
    print("ایجاد کاربران تست...")
    
    # کاربر سازمان مرکزی
    user_central = User.query.filter_by(sso_id='test_central').first()
    if not user_central:
        user_central = User(
            sso_id='test_central',
            name='کاربر مرکزی تست',
            email='central@test.com'
        )
        db.session.add(user_central)
        db.session.flush()
        
        access = AccessLevel(level='central_org', user_id=user_central.id)
        db.session.add(access)
        print("  ✓ کاربر مرکزی ایجاد شد")
    else:
        print("  ✓ کاربر مرکزی از قبل موجود است")
    
    # کاربر دانشگاه استان
    user_province = User.query.filter_by(sso_id='test_province').first()
    if not user_province:
        user_province = User(
            sso_id='test_province',
            name='کاربر استان تست',
            email='province@test.com',
            province_code=1  # تهران
        )
        db.session.add(user_province)
        db.session.flush()
        
        access = AccessLevel(level='province_university', user_id=user_province.id)
        db.session.add(access)
        print("  ✓ کاربر استان ایجاد شد")
    else:
        print("  ✓ کاربر استان از قبل موجود است")
    
    # کاربر دانشکده
    user_faculty = User.query.filter_by(sso_id='test_faculty').first()
    if not user_faculty:
        user_faculty = User(
            sso_id='test_faculty',
            name='کاربر دانشکده تست',
            email='faculty@test.com',
            province_code=1,
            faculty_code=1001
        )
        db.session.add(user_faculty)
        db.session.flush()
        
        access = AccessLevel(level='faculty', user_id=user_faculty.id)
        db.session.add(access)
        print("  ✓ کاربر دانشکده ایجاد شد")
    else:
        print("  ✓ کاربر دانشکده از قبل موجود است")
    
    db.session.commit()
    return user_central, user_province, user_faculty

def test_user_access():
    """تست دسترسی کاربران"""
    with app.app_context():
        # ایجاد کاربران
        user_central, user_province, user_faculty = create_test_users()
        
        print("\n" + "=" * 60)
        print("تست دسترسی کاربران به داشبوردها")
        print("=" * 60)
        
        # تست کاربر سازمان مرکزی
        print("\n[1] تست کاربر سازمان مرکزی")
        print("-" * 60)
        context_central = UserContext(user_central, {})
        print(f"Access Level: {context_central.access_level.value}")
        print(f"Can filter by province: {context_central.data_filters['can_filter_by_province']}")
        print(f"Can filter by faculty: {context_central.data_filters['can_filter_by_faculty']}")
        
        # تست داشبوردها
        dashboards = DashboardRegistry.list_all()
        for dashboard in dashboards[:3]:  # فقط 3 داشبورد اول
            try:
                data = dashboard.get_data(context_central)
                print(f"  ✓ {dashboard.dashboard_id}: داده دریافت شد ({len(data)} آیتم)")
            except Exception as e:
                print(f"  ✗ {dashboard.dashboard_id}: خطا - {str(e)[:50]}")
        
        # تست کاربر دانشگاه استان
        print("\n[2] تست کاربر دانشگاه استان")
        print("-" * 60)
        context_province = UserContext(user_province, {})
        print(f"Access Level: {context_province.access_level.value}")
        print(f"Province Code: {context_province.province_code}")
        print(f"Can filter by province: {context_province.data_filters['can_filter_by_province']}")
        
        for dashboard in dashboards[:3]:
            try:
                data = dashboard.get_data(context_province)
                print(f"  ✓ {dashboard.dashboard_id}: داده دریافت شد ({len(data)} آیتم)")
            except Exception as e:
                print(f"  ✗ {dashboard.dashboard_id}: خطا - {str(e)[:50]}")
        
        # تست کاربر دانشکده
        print("\n[3] تست کاربر دانشکده")
        print("-" * 60)
        context_faculty = UserContext(user_faculty, {})
        print(f"Access Level: {context_faculty.access_level.value}")
        print(f"Faculty Code: {context_faculty.faculty_code}")
        print(f"Can filter by province: {context_faculty.data_filters['can_filter_by_province']}")
        
        for dashboard in dashboards[:3]:
            try:
                data = dashboard.get_data(context_faculty)
                print(f"  ✓ {dashboard.dashboard_id}: داده دریافت شد ({len(data)} آیتم)")
            except Exception as e:
                print(f"  ✗ {dashboard.dashboard_id}: خطا - {str(e)[:50]}")
        
        # تست فیلترها
        print("\n[4] تست فیلترها")
        print("-" * 60)
        dashboard = DashboardRegistry.get('d1')
        if dashboard:
            # تست با فیلتر استان
            filters = {'province_code': 1}
            try:
                data = dashboard.get_data(context_central, filters=filters)
                print(f"  ✓ فیلتر استان: داده دریافت شد")
            except Exception as e:
                print(f"  ✗ فیلتر استان: خطا - {str(e)[:50]}")
            
            # تست با فیلتر دانشکده
            filters = {'faculty_code': 1001}
            try:
                data = dashboard.get_data(context_central, filters=filters)
                print(f"  ✓ فیلتر دانشکده: داده دریافت شد")
            except Exception as e:
                print(f"  ✗ فیلتر دانشکده: خطا - {str(e)[:50]}")
        
        print("\n" + "=" * 60)
        print("✓ تست‌ها کامل شد!")
        print("=" * 60)

if __name__ == '__main__':
    test_user_access()


