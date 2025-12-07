"""
LMS Data Sync - Single Run Version
Fetches LMS data once and stores it in database
"""
import requests
import sqlite3
from datetime import datetime
import urllib3
import sys
import os

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Default URLs (can be overridden)
DEFAULT_URLS = {
    "Zone1": "https://lms1.cfu.ac.ir/mod/adobeconnect/monitor.php",
    "Zone2": "https://lms2.cfu.ac.ir/mod/adobeconnect/monitor.php",
    "Zone3": "https://lms3.cfu.ac.ir/mod/adobeconnect/monitor.php",
    "Zone4": "https://lms4.cfu.ac.ir/mod/adobeconnect/monitor.php",
    "Zone5": "https://lms5.cfu.ac.ir/mod/adobeconnect/monitor.php",
    "Zone6": "https://lms6.cfu.ac.ir/mod/adobeconnect/monitor.php",
    "Zone7": "https://lms7.cfu.ac.ir/mod/adobeconnect/monitor.php",
    "Zone8": "https://lms8.cfu.ac.ir/mod/adobeconnect/monitor.php",
    "Zone9": "https://lms9.cfu.ac.ir/mod/adobeconnect/monitor.php",
    "Zone10": "https://lms10.cfu.ac.ir/mod/adobeconnect/monitor.php",
    "Zone11": "https://meeting.cfu.ac.ir/mod/adobeconnect/monitor.php",
}

# Get absolute path to database file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "faculty_data.db")

def init_db():
    """Initialize database"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS monitor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT,
            timestamp DATETIME,
            key TEXT,
            value INTEGER
        )
    """)
    conn.commit()
    conn.close()

def fetch_data(url):
    """Fetch data from URL"""
    try:
        response = requests.get(url, timeout=10, verify=False)
        response.raise_for_status()
        return response.text.strip()
    except Exception as e:
        print(f"[ERROR] Error fetching {url}: {e}")
        return None

def parse_data(data):
    """
    Parse data string into key-value pairs
    Input: 'online_lms_user 20 online_adobe_class 0 ...'
    Output: [('online_lms_user', 20), ('online_adobe_class', 0), ...]
    """
    if not data:
        return []
    parts = data.split()
    return [(parts[i], int(parts[i+1])) for i in range(0, len(parts), 2)]

def store_data(url, parsed_data):
    """Store parsed data in database"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    timestamp = datetime.now()
    for key, value in parsed_data:
        cur.execute("INSERT INTO monitor_data (url, timestamp, key, value) VALUES (?, ?, ?, ?)",
                    (url, timestamp, key, value))
    conn.commit()
    conn.close()

def sync_lms_data(urls=None):
    """
    Sync LMS data from given URLs (or default URLs)
    Returns: (success: bool, records_count: int)
    """
    if urls is None:
        urls = DEFAULT_URLS
    
    init_db()
    total_records = 0
    
    print("[INFO] Starting LMS data sync...")
    
    for zone_name, url in urls.items():
        print(f"[INFO] Fetching data from {zone_name}: {url}")
        raw_data = fetch_data(url)
        if raw_data:
            parsed = parse_data(raw_data)
            if parsed:
                store_data(url, parsed)
                records_count = len(parsed)
                total_records += records_count
                print(f"[INFO] Stored {records_count} records from {zone_name} at {datetime.now()}")
            else:
                print(f"[WARNING] No data parsed from {zone_name}")
        else:
            print(f"[WARNING] Failed to fetch data from {zone_name}")
    
    print(f"[INFO] LMS sync completed. Total records: {total_records}")
    return True, total_records

def main():
    """Main function for command-line execution"""
    # Check if custom URL is provided as argument
    if len(sys.argv) > 1:
        custom_url = sys.argv[1]
        urls = {"Custom": custom_url}
        success, count = sync_lms_data(urls)
    else:
        success, count = sync_lms_data()
    
    if success:
        print(f"[SUCCESS] Sync completed with {count} records")
        sys.exit(0)
    else:
        print("[ERROR] Sync failed")
        sys.exit(1)

if __name__ == "__main__":
    main()


