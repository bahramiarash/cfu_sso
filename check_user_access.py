"""
Script to check user dashboard access
Usage: python check_user_access.py <sso_id>
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app import app
from models import User
from admin_models import DashboardAccess, DashboardConfig
from extensions import db
from dashboards.context import UserContext, AccessLevel

def check_user_access(sso_id):
    """Check user's dashboard access"""
    with app.app_context():
        # Find user
        user = User.query.filter_by(sso_id=sso_id.lower()).first()
        if not user:
            print(f"❌ کاربر با SSO ID '{sso_id}' یافت نشد")
            return
        
        print(f"✅ کاربر یافت شد: {user.name} (ID: {user.id})")
        print(f"   SSO ID: {user.sso_id}")
        print(f"   Email: {user.email or 'ندارد'}")
        print()
        
        # Check if user is admin
        is_admin = user.is_admin()
        print(f"🔐 وضعیت Admin: {'✅ بله' if is_admin else '❌ خیر'}")
        if is_admin:
            print("   → کاربر admin است و به همه داشبوردها دسترسی دارد")
            print()
        
        # Check access levels
        access_levels = [acc.level for acc in user.access_levels]
        print(f"📋 Access Levels: {access_levels if access_levels else 'ندارد'}")
        print()
        
        # Create user context to check access level
        try:
            user_context = UserContext(user, {})
            print(f"🎯 Access Level تعیین شده: {user_context.access_level.value}")
            print()
        except Exception as e:
            print(f"⚠️ خطا در ایجاد UserContext: {e}")
            print()
        
        # Check dashboard access records
        dashboard_accesses = DashboardAccess.query.filter_by(user_id=user.id).all()
        print(f"📊 رکوردهای دسترسی داشبورد: {len(dashboard_accesses)} مورد")
        
        if dashboard_accesses:
            print("\nرکوردهای دسترسی:")
            for access in dashboard_accesses:
                status = "✅ دسترسی دارد" if access.can_access else "❌ دسترسی ندارد"
                print(f"  - داشبورد: {access.dashboard_id} → {status}")
                if access.filter_restrictions:
                    print(f"    محدودیت‌ها: {access.filter_restrictions}")
                if access.date_from or access.date_to:
                    print(f"    محدودیت زمانی: از {access.date_from} تا {access.date_to}")
        else:
            print("  → هیچ رکورد دسترسی خاصی وجود ندارد")
        print()
        
        # Check public dashboards
        public_dashboards = DashboardConfig.query.filter_by(is_public=True).all()
        print(f"🌐 داشبوردهای Public: {len(public_dashboards)} مورد")
        if public_dashboards:
            for config in public_dashboards:
                print(f"  - {config.dashboard_id}: {config.title}")
        else:
            print("  → هیچ داشبورد public وجود ندارد")
        print()
        
        # Summary
        print("=" * 60)
        print("خلاصه:")
        if is_admin:
            print("✅ کاربر admin است → دسترسی به همه داشبوردها")
        elif dashboard_accesses:
            accessible = [a for a in dashboard_accesses if a.can_access]
            if accessible:
                print(f"✅ کاربر به {len(accessible)} داشبورد دسترسی دارد")
            else:
                print("❌ کاربر به هیچ داشبوردی دسترسی ندارد (همه رکوردها can_access=False)")
        elif public_dashboards:
            print(f"✅ کاربر می‌تواند به {len(public_dashboards)} داشبورد public دسترسی داشته باشد")
        else:
            print("❌ کاربر به هیچ داشبوردی دسترسی ندارد")
            print("   راه حل: یکی از موارد زیر را انجام دهید:")
            print("   1. کاربر را admin کنید")
            print("   2. رکورد دسترسی در dashboard_access ایجاد کنید")
            print("   3. داشبورد را public کنید")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_user_access.py <sso_id>")
        print("Example: python check_user_access.py asef")
        sys.exit(1)
    
    sso_id = sys.argv[1]
    check_user_access(sso_id)




