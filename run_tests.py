"""
اسکریپت اجرای تست‌های سریع
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app import app
from dashboards.registry import DashboardRegistry

def run_quick_tests():
    """اجرای تست‌های سریع"""
    print("=" * 60)
    print("تست سریع سیستم داشبوردها")
    print("=" * 60)
    
    with app.app_context():
        # تست 1: Registry
        print("\n[1] تست Dashboard Registry...")
        dashboards = DashboardRegistry.list_all()
        print(f"   ✓ {len(dashboards)} داشبورد ثبت شده:")
        for dash in dashboards:
            print(f"      - {dash.dashboard_id}: {dash.title}")
        
        # تست 2: بررسی داشبوردهای خاص
        print("\n[2] بررسی داشبوردهای اصلی...")
        required_dashboards = ['d1', 'd2', 'd3', 'd7', 'd8']
        for dash_id in required_dashboards:
            dash = DashboardRegistry.get(dash_id)
            if dash:
                print(f"   ✓ {dash_id}: موجود")
            else:
                print(f"   ✗ {dash_id}: یافت نشد")
        
        # تست 3: بررسی Data Providers
        print("\n[3] بررسی Data Providers...")
        try:
            from dashboards.data_providers import (
                FacultyDataProvider,
                StudentsDataProvider,
                PardisDataProvider,
                LMSDataProvider
            )
            print("   ✓ FacultyDataProvider: موجود")
            print("   ✓ StudentsDataProvider: موجود")
            print("   ✓ PardisDataProvider: موجود")
            print("   ✓ LMSDataProvider: موجود")
        except ImportError as e:
            print(f"   ✗ خطا در import: {e}")
        
        # تست 4: بررسی Context
        print("\n[4] بررسی UserContext...")
        try:
            from dashboards.context import UserContext, AccessLevel
            print("   ✓ UserContext: موجود")
            print("   ✓ AccessLevel: موجود")
            print(f"   ✓ سطوح دسترسی: {[level.value for level in AccessLevel]}")
        except ImportError as e:
            print(f"   ✗ خطا در import: {e}")
        
        # تست 5: بررسی Config
        print("\n[5] بررسی Configuration...")
        try:
            from dashboards.config import DashboardConfig
            print(f"   ✓ Faculty DB: {DashboardConfig.FACULTY_DB}")
            print(f"   ✓ Cache Enabled: {DashboardConfig.CACHE_ENABLED}")
            print(f"   ✓ Cache TTL: {DashboardConfig.CACHE_TTL} seconds")
        except Exception as e:
            print(f"   ✗ خطا: {e}")
        
        print("\n" + "=" * 60)
        print("✓ تست‌های سریع کامل شد!")
        print("=" * 60)
        print("\nبرای تست کامل‌تر، از test_user_access.py استفاده کنید:")
        print("  python test_user_access.py")

if __name__ == '__main__':
    run_quick_tests()


