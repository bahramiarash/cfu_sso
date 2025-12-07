"""
Migration: Create admin panel tables
Creates tables for DashboardAccess, AccessLog, DataSync, and DashboardConfig
"""
import sqlite3
import os
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'access_control.db')

def migrate():
    """Create admin panel tables"""
    print("Starting admin panel migration...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Create dashboard_access table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dashboard_access (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                dashboard_id VARCHAR(100) NOT NULL,
                can_access BOOLEAN NOT NULL DEFAULT 1,
                filter_restrictions TEXT,
                date_from DATETIME,
                date_to DATETIME,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        """)
        print("[OK] Created dashboard_access table")
        
        # Create access_logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS access_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action VARCHAR(100) NOT NULL,
                resource_type VARCHAR(50),
                resource_id VARCHAR(100),
                ip_address VARCHAR(45),
                user_agent TEXT,
                request_path VARCHAR(500),
                request_method VARCHAR(10),
                details TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        print("[OK] Created access_logs table")
        
        # Create data_syncs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS data_syncs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_source VARCHAR(100) NOT NULL UNIQUE,
                sync_type VARCHAR(50) NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'pending',
                last_sync_at DATETIME,
                next_sync_at DATETIME,
                auto_sync_enabled BOOLEAN NOT NULL DEFAULT 1,
                sync_interval_minutes INTEGER NOT NULL DEFAULT 60,
                api_endpoint VARCHAR(500),
                api_method VARCHAR(10) NOT NULL DEFAULT 'GET',
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
        print("[OK] Created data_syncs table")
        
        # Create dashboard_configs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dashboard_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dashboard_id VARCHAR(100) UNIQUE NOT NULL,
                title VARCHAR(200) NOT NULL,
                description TEXT,
                icon VARCHAR(100),
                `order` INTEGER NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                is_public BOOLEAN NOT NULL DEFAULT 0,
                cache_ttl_seconds INTEGER NOT NULL DEFAULT 300,
                refresh_interval_seconds INTEGER,
                config TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        """)
        print("[OK] Created dashboard_configs table")
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dashboard_access_user ON dashboard_access(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dashboard_access_dashboard ON dashboard_access(dashboard_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_access_logs_user ON access_logs(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_access_logs_created_at ON access_logs(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_data_syncs_source ON data_syncs(data_source)")
        print("[OK] Created indexes")
        
        # Insert default data syncs
        default_syncs = [
            ('faculty', 'manual', 'pending', 'https://api.cfu.ac.ir/API/Golestan/Faculty', 'POST'),
            ('students', 'manual', 'pending', 'https://api.cfu.ac.ir/API/Golestan/Students_2', 'POST'),
            ('lms', 'manual', 'pending', 'https://api.example.com/lms', 'GET'),
        ]
        
        for data_source, sync_type, status, api_endpoint, api_method in default_syncs:
            cursor.execute("""
                INSERT OR IGNORE INTO data_syncs 
                (data_source, sync_type, status, api_endpoint, api_method)
                VALUES (?, ?, ?, ?, ?)
            """, (data_source, sync_type, status, api_endpoint, api_method))
        
        print("[OK] Inserted default data syncs")
        
        conn.commit()
        print("\n[SUCCESS] Admin panel migration completed successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    migrate()

