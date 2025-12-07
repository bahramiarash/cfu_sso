"""
Migration: Add sync_interval_unit and change sync_interval_minutes to sync_interval_value
"""
import sqlite3
import os

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'access_control.db')

def migrate():
    """Add sync_interval_unit and update sync_interval structure"""
    print("Starting migration: Add sync interval unit...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(data_syncs)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Add sync_interval_unit if not exists
        if 'sync_interval_unit' not in columns:
            cursor.execute("ALTER TABLE data_syncs ADD COLUMN sync_interval_unit VARCHAR(20) DEFAULT 'minutes'")
            print("[OK] Added sync_interval_unit column")
        else:
            print("[SKIP] sync_interval_unit column already exists")
        
        # Rename sync_interval_minutes to sync_interval_value if needed
        if 'sync_interval_minutes' in columns and 'sync_interval_value' not in columns:
            # SQLite doesn't support ALTER COLUMN RENAME, so we need to recreate
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS data_syncs_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_source VARCHAR(100) NOT NULL UNIQUE,
                    sync_type VARCHAR(50) NOT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'pending',
                    last_sync_at DATETIME,
                    next_sync_at DATETIME,
                    auto_sync_enabled BOOLEAN NOT NULL DEFAULT 1,
                    sync_interval_value INTEGER NOT NULL DEFAULT 60,
                    sync_interval_unit VARCHAR(20) DEFAULT 'minutes',
                    api_base_url VARCHAR(500),
                    api_endpoint VARCHAR(500),
                    api_method VARCHAR(10) NOT NULL DEFAULT 'GET',
                    api_username VARCHAR(200),
                    api_password VARCHAR(500),
                    api_params TEXT,
                    records_synced INTEGER NOT NULL DEFAULT 0,
                    sync_duration_seconds REAL,
                    error_message TEXT,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_synced_by INTEGER,
                    FOREIGN KEY (last_synced_by) REFERENCES users(id)
                )
            """)
            
            # Copy data
            cursor.execute("""
                INSERT INTO data_syncs_new 
                (id, data_source, sync_type, status, last_sync_at, next_sync_at,
                 auto_sync_enabled, sync_interval_value, sync_interval_unit,
                 api_base_url, api_endpoint, api_method, api_username, api_password,
                 api_params, records_synced, sync_duration_seconds, error_message,
                 created_at, updated_at, last_synced_by)
                SELECT id, data_source, sync_type, status, last_sync_at, next_sync_at,
                       auto_sync_enabled, sync_interval_minutes, COALESCE(sync_interval_unit, 'minutes'),
                       api_base_url, api_endpoint, api_method, api_username, api_password,
                       api_params, records_synced, sync_duration_seconds, error_message,
                       created_at, updated_at, last_synced_by
                FROM data_syncs
            """)
            
            # Drop old table and rename new one
            cursor.execute("DROP TABLE data_syncs")
            cursor.execute("ALTER TABLE data_syncs_new RENAME TO data_syncs")
            
            # Recreate indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_data_syncs_source ON data_syncs(data_source)")
            
            print("[OK] Renamed sync_interval_minutes to sync_interval_value")
        elif 'sync_interval_value' in columns:
            print("[SKIP] sync_interval_value column already exists")
        
        conn.commit()
        print("\n[SUCCESS] Migration completed successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    migrate()


