"""
Quick LMS Sync Script
Run this script to immediately sync LMS data
"""
import sys
import os

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

# Import sync function
from fetch_data.lms_sync import sync_lms_data
import jdatetime
from datetime import datetime

print("=" * 60)
print("LMS Data Sync - Manual Execution")
print("=" * 60)
print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
today_jalali = jdatetime.datetime.now()
print(f"Jalali Date: {today_jalali.strftime('%Y/%m/%d %H:%M:%S')}")
print("=" * 60)
print()

try:
    success, records_count = sync_lms_data()
    
    if success:
        print()
        print("=" * 60)
        print(f"SUCCESS: Sync completed!")
        print(f"Total records stored: {records_count}")
        print("=" * 60)
        sys.exit(0)
    else:
        print()
        print("=" * 60)
        print("ERROR: Sync failed!")
        print("=" * 60)
        sys.exit(1)
except Exception as e:
    print()
    print("=" * 60)
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    print("=" * 60)
    sys.exit(1)

