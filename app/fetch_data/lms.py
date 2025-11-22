import requests
import sqlite3
import time
from datetime import datetime
import urllib3

# --- CONFIG ---
URLS = {
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
DB_FILE = "faculty_data.db"
FETCH_INTERVAL = 300  # seconds (5 minutes)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- DB SETUP ---
def init_db():
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

# --- FETCH + PARSE ---
def fetch_data(url):
    try:
        response = requests.get(url, timeout=10, verify=False)  # <-- SSL check disabled
        response.raise_for_status()
        return response.text.strip()
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

def parse_data(data):
    """
    Input: 'online_lms_user 20 online_adobe_class 0 ...'
    Output: [('online_lms_user', 20), ('online_adobe_class', 0), ...]
    """
    parts = data.split()
    return [(parts[i], int(parts[i+1])) for i in range(0, len(parts), 2)]

# --- STORE ---
def store_data(url, parsed_data):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    timestamp = datetime.now()
    for key, value in parsed_data:
        cur.execute("INSERT INTO monitor_data (url, timestamp, key, value) VALUES (?, ?, ?, ?)",
                    (url, timestamp, key, value))
    conn.commit()
    conn.close()

# --- MAIN LOOP ---
def main():
    init_db()
    while True:
        for z in URLS:
            raw_data = fetch_data(URLS[z])
            if raw_data:
                parsed = parse_data(raw_data)
                store_data(z, parsed)
                print(f"Stored data from {URLS[z]} at {datetime.now()}")
        time.sleep(FETCH_INTERVAL)

if __name__ == "__main__":
    main()
