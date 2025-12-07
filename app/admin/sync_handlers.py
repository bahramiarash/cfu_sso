"""
Data Sync Handlers
Handles actual data synchronization by calling fetch scripts
"""
import subprocess
import os
import sys
import logging
import threading
from datetime import datetime
from extensions import db
from admin_models import DataSync
from models import User
from .sync_progress import update_sync_progress, add_sync_log, clear_sync_progress

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FETCH_DATA_DIR = os.path.join(BASE_DIR, 'fetch_data')


def run_faculty_sync(user_id=None, sync_id=None):
    """
    Run faculty data sync by executing faculty_main.py
    Returns: (success: bool, records_count: int, error_message: str)
    """
    sync = DataSync.query.filter_by(data_source='faculty').first() if not sync_id else DataSync.query.get(sync_id)
    if not sync:
        return False, 0, "Faculty sync configuration not found"
    
    sync_id = sync.id
    
    try:
        # Initialize progress tracking
        update_sync_progress(sync_id, status='running', current_step='شروع همگام‌سازی...', progress=0)
        add_sync_log(sync_id, 'شروع همگام‌سازی داده‌های اعضای هیئت علمی', 'info')
        
        # Update sync status
        sync.status = 'running'
        sync.last_synced_by = user_id
        db.session.commit()
        
        # Run the fetch script
        script_path = os.path.join(FETCH_DATA_DIR, 'faculty_main.py')
        start_time = datetime.utcnow()
        
        update_sync_progress(sync_id, current_step='در حال اجرای اسکریپت...', progress=10)
        add_sync_log(sync_id, f'اجرای فایل: {script_path}', 'info')
        
        # Create a process with real-time output monitoring
        process = subprocess.Popen(
            [sys.executable, script_path],
            cwd=FETCH_DATA_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Monitor output in real-time
        output_lines = []
        records_count = 0
        
        def monitor_output():
            nonlocal records_count
            try:
                for line in process.stdout:
                    output_lines.append(line)
                    line = line.strip()
                    
                    # Parse progress information
                    if '[INFO]' in line:
                        add_sync_log(sync_id, line.replace('[INFO]', '').strip(), 'info')
                        
                        # Check for record count
                        if 'faculty records inserted' in line or 'faculty records inserted/updated' in line:
                            try:
                                parts = line.split()
                                for part in parts:
                                    if part.isdigit():
                                        records_count = int(part)
                                        update_sync_progress(
                                            sync_id, 
                                            records_processed=records_count,
                                            progress=90,
                                            current_step=f'دریافت {records_count} رکورد'
                                        )
                                        break
                            except:
                                pass
                    
                    elif '[ERROR]' in line:
                        add_sync_log(sync_id, line.replace('[ERROR]', '').strip(), 'error')
            except Exception as e:
                logger.error(f"Error monitoring output: {e}")
        
        # Start monitoring in a separate thread
        monitor_thread = threading.Thread(target=monitor_output, daemon=True)
        monitor_thread.start()
        
        # Wait for process to complete with timeout
        try:
            process.wait(timeout=3600)  # 1 hour timeout
            result_code = process.returncode
            stderr_output = process.stderr.read() if process.stderr else ''
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise subprocess.TimeoutExpired(process.args, 3600)
        
        result = type('Result', (), {
            'returncode': result_code,
            'stdout': '\n'.join(output_lines),
            'stderr': stderr_output
        })()
        
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        if result.returncode == 0:
            # If we couldn't parse the count, try to get it from database
            if records_count == 0:
                try:
                    import sqlite3
                    db_path = os.path.join(FETCH_DATA_DIR, 'faculty_data.db')
                    if os.path.exists(db_path):
                        conn = sqlite3.connect(db_path)
                        cursor = conn.cursor()
                        cursor.execute("SELECT COUNT(*) FROM faculty")
                        records_count = cursor.fetchone()[0]
                        conn.close()
                except:
                    pass
            
            # Update progress
            update_sync_progress(
                sync_id,
                status='success',
                progress=100,
                records_processed=records_count,
                current_step=f'همگام‌سازی با موفقیت انجام شد: {records_count} رکورد'
            )
            add_sync_log(sync_id, f'همگام‌سازی با موفقیت انجام شد. تعداد رکوردها: {records_count}', 'success')
            
            # Update sync status
            sync.status = 'success'
            sync.last_sync_at = end_time
            sync.records_synced = records_count
            sync.sync_duration_seconds = duration
            sync.error_message = None
            
            # Calculate next sync time if auto sync is enabled
            if sync.auto_sync_enabled:
                from datetime import timedelta
                interval_minutes = sync.get_interval_minutes()
                sync.next_sync_at = end_time + timedelta(minutes=interval_minutes)
            
            db.session.commit()
            logger.info(f"Faculty sync completed successfully: {records_count} records in {duration:.2f}s")
            
            # Clear progress after a delay
            threading.Timer(300, clear_sync_progress, args=[sync_id]).start()  # Clear after 5 minutes
            
            return True, records_count, None
            
        else:
            error_msg = result.stderr or result.stdout or "Unknown error"
            update_sync_progress(sync_id, status='failed', progress=0, current_step='خطا در همگام‌سازی')
            add_sync_log(sync_id, f'خطا: {error_msg[:200]}', 'error')
            
            sync.status = 'failed'
            sync.error_message = error_msg[:500]  # Limit error message length
            sync.sync_duration_seconds = duration
            db.session.commit()
            logger.error(f"Faculty sync failed: {error_msg}")
            
            threading.Timer(300, clear_sync_progress, args=[sync_id]).start()
            return False, 0, error_msg
            
    except subprocess.TimeoutExpired:
        update_sync_progress(sync_id, status='failed', progress=0, current_step='Timeout: همگام‌سازی بیش از 1 ساعت طول کشید')
        add_sync_log(sync_id, 'خطا: همگام‌سازی بیش از 1 ساعت طول کشید', 'error')
        
        sync.status = 'failed'
        sync.error_message = "Sync timeout after 1 hour"
        db.session.commit()
        logger.error("Faculty sync timeout")
        
        threading.Timer(300, clear_sync_progress, args=[sync_id]).start()
        return False, 0, "Sync timeout after 1 hour"
        
    except Exception as e:
        error_msg = str(e)
        update_sync_progress(sync_id, status='failed', progress=0, current_step=f'خطا: {error_msg[:100]}')
        add_sync_log(sync_id, f'خطا: {error_msg}', 'error')
        
        sync.status = 'failed'
        sync.error_message = error_msg[:500]
        db.session.commit()
        logger.error(f"Faculty sync error: {error_msg}", exc_info=True)
        
        threading.Timer(300, clear_sync_progress, args=[sync_id]).start()
        return False, 0, error_msg


def run_students_sync(user_id=None, sync_id=None):
    """
    Run students data sync by executing students_main.py
    Returns: (success: bool, records_count: int, error_message: str)
    """
    sync = DataSync.query.filter_by(data_source='students').first() if not sync_id else DataSync.query.get(sync_id)
    if not sync:
        return False, 0, "Students sync configuration not found"
    
    sync_id = sync.id
    
    try:
        # Initialize progress tracking
        update_sync_progress(sync_id, status='running', current_step='شروع همگام‌سازی...', progress=0)
        add_sync_log(sync_id, 'شروع همگام‌سازی داده‌های دانشجویان', 'info')
        
        # Update sync status
        sync.status = 'running'
        sync.last_synced_by = user_id
        db.session.commit()
        
        # Run the fetch script
        script_path = os.path.join(FETCH_DATA_DIR, 'students_main.py')
        start_time = datetime.utcnow()
        
        update_sync_progress(sync_id, current_step='در حال اجرای اسکریپت...', progress=5)
        add_sync_log(sync_id, f'اجرای فایل: {script_path}', 'info')
        
        # Create a process with real-time output monitoring
        process = subprocess.Popen(
            [sys.executable, script_path],
            cwd=FETCH_DATA_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Monitor output in real-time
        output_lines = []
        records_count = 0
        total_pardis = 0
        processed_pardis = 0
        current_pardis = None
        current_term = None
        
        def monitor_output():
            nonlocal records_count, total_pardis, processed_pardis, current_pardis, current_term
            try:
                for line in process.stdout:
                    output_lines.append(line)
                    line = line.strip()
                    
                    # Parse progress information
                    if 'Fetching for Pardis' in line:
                        # Extract pardis and term
                        try:
                            parts = line.split('Pardis')
                            if len(parts) > 1:
                                pardis_part = parts[1].split(',')[0].strip()
                                term_part = line.split('Term')[1].strip() if 'Term' in line else ''
                                current_pardis = pardis_part
                                current_term = term_part
                                
                                processed_pardis += 1
                                progress = min(5 + int((processed_pardis / max(total_pardis, 1)) * 90), 95)
                                update_sync_progress(
                                    sync_id,
                                    progress=progress,
                                    current_step=f'در حال دریافت از پردیس {current_pardis}, ترم {current_term}...',
                                    records_processed=records_count
                                )
                                add_sync_log(sync_id, f'در حال دریافت: پردیس {current_pardis}, ترم {current_term}', 'info')
                        except:
                            pass
                    
                    elif 'Students count:' in line:
                        try:
                            parts = line.split(':')
                            if len(parts) > 1:
                                count = int(parts[1].strip())
                                records_count += count
                                update_sync_progress(
                                    sync_id,
                                    records_processed=records_count,
                                    current_step=f'دریافت {records_count} رکورد تاکنون (پردیس {current_pardis or "..."})'
                                )
                        except:
                            pass
                    
                    elif '[ERROR]' in line or 'error' in line.lower():
                        add_sync_log(sync_id, line, 'error')
                    
                    elif 'All done' in line:
                        add_sync_log(sync_id, 'همگام‌سازی کامل شد', 'success')
            except Exception as e:
                logger.error(f"Error monitoring output: {e}")
        
        # Get total pardis count for progress calculation
        try:
            import sqlite3
            db_path2 = os.path.join(BASE_DIR, 'access_control.db')
            if os.path.exists(db_path2):
                conn2 = sqlite3.connect(db_path2)
                cursor2 = conn2.cursor()
                cursor2.execute("SELECT COUNT(*) FROM pardis")
                total_pardis = cursor2.fetchone()[0] * 15  # Approximate: 15 terms per pardis
                conn2.close()
        except:
            total_pardis = 100  # Default estimate
        
        # Start monitoring in a separate thread
        monitor_thread = threading.Thread(target=monitor_output, daemon=True)
        monitor_thread.start()
        
        # Wait for process to complete with timeout
        try:
            process.wait(timeout=7200)  # 2 hours timeout
            result_code = process.returncode
            stderr_output = process.stderr.read() if process.stderr else ''
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise subprocess.TimeoutExpired(process.args, 7200)
        
        result = type('Result', (), {
            'returncode': result_code,
            'stdout': '\n'.join(output_lines),
            'stderr': stderr_output
        })()
        
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        if result.returncode == 0:
            # If we couldn't parse the count, try to get it from database
            if records_count == 0:
                try:
                    import sqlite3
                    db_path = os.path.join(FETCH_DATA_DIR, 'faculty_data.db')
                    if os.path.exists(db_path):
                        conn = sqlite3.connect(db_path)
                        cursor = conn.cursor()
                        cursor.execute("SELECT COUNT(*) FROM Students")
                        records_count = cursor.fetchone()[0]
                        conn.close()
                except:
                    pass
            
            # Update progress
            update_sync_progress(
                sync_id,
                status='success',
                progress=100,
                records_processed=records_count,
                current_step=f'همگام‌سازی با موفقیت انجام شد: {records_count} رکورد'
            )
            add_sync_log(sync_id, f'همگام‌سازی با موفقیت انجام شد. تعداد رکوردها: {records_count}', 'success')
            
            # Update sync status
            sync.status = 'success'
            sync.last_sync_at = end_time
            sync.records_synced = records_count
            sync.sync_duration_seconds = duration
            sync.error_message = None
            
            # Calculate next sync time if auto sync is enabled
            if sync.auto_sync_enabled:
                from datetime import timedelta
                interval_minutes = sync.get_interval_minutes()
                sync.next_sync_at = end_time + timedelta(minutes=interval_minutes)
            
            db.session.commit()
            logger.info(f"Students sync completed successfully: {records_count} records in {duration:.2f}s")
            
            # Clear progress after a delay
            threading.Timer(300, clear_sync_progress, args=[sync_id]).start()  # Clear after 5 minutes
            
            return True, records_count, None
            
        else:
            error_msg = result.stderr or result.stdout or "Unknown error"
            update_sync_progress(sync_id, status='failed', progress=0, current_step='خطا در همگام‌سازی')
            add_sync_log(sync_id, f'خطا: {error_msg[:200]}', 'error')
            
            sync.status = 'failed'
            sync.error_message = error_msg[:500]
            sync.sync_duration_seconds = duration
            db.session.commit()
            logger.error(f"Students sync failed: {error_msg}")
            
            threading.Timer(300, clear_sync_progress, args=[sync_id]).start()
            return False, 0, error_msg
            
    except subprocess.TimeoutExpired:
        update_sync_progress(sync_id, status='failed', progress=0, current_step='Timeout: همگام‌سازی بیش از 2 ساعت طول کشید')
        add_sync_log(sync_id, 'خطا: همگام‌سازی بیش از 2 ساعت طول کشید', 'error')
        
        sync.status = 'failed'
        sync.error_message = "Sync timeout after 2 hours"
        db.session.commit()
        logger.error("Students sync timeout")
        
        threading.Timer(300, clear_sync_progress, args=[sync_id]).start()
        return False, 0, "Sync timeout after 2 hours"
        
    except Exception as e:
        error_msg = str(e)
        update_sync_progress(sync_id, status='failed', progress=0, current_step=f'خطا: {error_msg[:100]}')
        add_sync_log(sync_id, f'خطا: {error_msg}', 'error')
        
        sync.status = 'failed'
        sync.error_message = error_msg[:500]
        db.session.commit()
        logger.error(f"Students sync error: {error_msg}", exc_info=True)
        
        threading.Timer(300, clear_sync_progress, args=[sync_id]).start()
        return False, 0, error_msg


# Global variable to track LMS continuous sync thread
_lms_continuous_thread = None
_lms_continuous_running = False

def stop_lms_continuous_sync():
    """
    Stop LMS continuous sync thread
    Returns: (success: bool, message: str)
    """
    global _lms_continuous_thread, _lms_continuous_running
    
    try:
        # Check if thread is actually running (check both flag and thread status)
        thread_is_alive = _lms_continuous_thread and _lms_continuous_thread.is_alive()
        is_running = _lms_continuous_running or thread_is_alive
        
        if not is_running:
            return False, "همگام‌سازی مداوم LMS در حال اجرا نیست"
        
        logger.info("Stopping LMS continuous sync...")
        
        # Set flag to stop the loop
        _lms_continuous_running = False
        
        # Wait a bit for thread to finish gracefully
        if thread_is_alive:
            import time
            logger.info("Waiting for LMS sync thread to finish...")
            _lms_continuous_thread.join(timeout=5)
            
            # Check if thread is still alive after timeout
            if _lms_continuous_thread.is_alive():
                logger.warning("LMS sync thread did not stop gracefully within timeout")
                # Thread will stop on next iteration due to flag being False
        
        # Update sync status
        sync = DataSync.query.filter_by(data_source='lms').first()
        if sync:
            sync.status = 'stopped'
            db.session.commit()
            logger.info(f"LMS sync status updated to 'stopped' in database")
        
        logger.info("LMS continuous sync stopped successfully")
        return True, "همگام‌سازی مداوم LMS با موفقیت متوقف شد"
    except Exception as e:
        logger.error(f"Error stopping LMS continuous sync: {e}", exc_info=True)
        return False, f"خطا در توقف همگام‌سازی: {str(e)}"

def check_and_restart_lms_continuous_sync():
    """
    Check if LMS continuous sync is running, restart if stopped
    This should be called periodically by scheduler
    """
    global _lms_continuous_thread, _lms_continuous_running
    
    try:
        sync = DataSync.query.filter_by(data_source='lms').first()
        if not sync or not sync.auto_sync_enabled:
            return False
        
        # Check if thread is alive
        if _lms_continuous_thread and _lms_continuous_thread.is_alive():
            return True  # Already running
        
        # Thread is not running, restart it
        logger.warning("LMS continuous sync thread is not running, restarting...")
        run_lms_sync(sync_id=sync.id)
        return True
    except Exception as e:
        logger.error(f"Error checking/restarting LMS continuous sync: {e}", exc_info=True)
        return False

def run_lms_sync(user_id=None, sync_id=None, manual_sync=False):
    """
    Run LMS data sync - starts continuous background sync if auto_sync is enabled
    If manual_sync is True, stops continuous sync first, performs manual sync, then restarts continuous sync
    
    Args:
        user_id: User ID triggering the sync
        sync_id: Specific sync ID (optional)
        manual_sync: If True, perform manual sync (stop continuous sync first)
    
    Returns: (success: bool, records_count: int, error_message: str)
    """
    global _lms_continuous_thread, _lms_continuous_running
    
    sync = DataSync.query.filter_by(data_source='lms').first() if not sync_id else DataSync.query.get(sync_id)
    if not sync:
        return False, 0, "LMS sync configuration not found"
    
    sync_id = sync.id
    auto_sync_was_running = False
    
    # If manual sync requested, stop continuous sync first
    if manual_sync:
        logger.info("Manual sync requested - stopping continuous sync first")
        if _lms_continuous_running or (_lms_continuous_thread and _lms_continuous_thread.is_alive()):
            auto_sync_was_running = True
            stop_success, stop_msg = stop_lms_continuous_sync()
            if stop_success:
                logger.info(f"Continuous sync stopped: {stop_msg}")
                # Wait a bit to ensure thread has stopped
                import time
                time.sleep(1)
            else:
                logger.warning(f"Could not stop continuous sync: {stop_msg}")
    
    # If auto_sync is enabled and not manual sync, start continuous background sync
    if sync.auto_sync_enabled and not manual_sync:
        # Check if continuous sync is already running
        if _lms_continuous_thread and _lms_continuous_thread.is_alive():
            logger.info("LMS continuous sync already running")
            update_sync_progress(sync_id, status='running', current_step='همگام‌سازی مداوم در حال اجرا است...', progress=50)
            add_sync_log(sync_id, 'همگام‌سازی مداوم LMS در حال اجرا است', 'info')
            return True, 0, None
        
        # Start continuous sync in background thread
        def continuous_lms_sync():
            """Continuous LMS sync loop"""
            global _lms_continuous_running
            _lms_continuous_running = True
            
            try:
                # Import lms module functions
                import sys
                import time
                sys.path.insert(0, FETCH_DATA_DIR)
                from lms import init_db, fetch_data, parse_data, store_data, URLS, FETCH_INTERVAL
                
                init_db()
                logger.info("LMS continuous sync started")
                update_sync_progress(sync_id, status='running', current_step='شروع همگام‌سازی مداوم...', progress=10)
                add_sync_log(sync_id, 'شروع همگام‌سازی مداوم LMS', 'info')
                
                # Update sync status - set next_sync_at to None for continuous sync
                from .scheduler import get_scheduler_app_context
                with get_scheduler_app_context():
                    sync_obj = DataSync.query.get(sync_id)
                    if sync_obj:
                        sync_obj.status = 'running'
                        sync_obj.next_sync_at = None  # Continuous sync doesn't need next_sync_at
                        db.session.commit()
                
                iteration = 0
                while _lms_continuous_running:
                    try:
                        iteration += 1
                        total_records = 0
                        
                        for zone_name, url in URLS.items():
                            try:
                                raw_data = fetch_data(url)
                                if raw_data:
                                    parsed = parse_data(raw_data)
                                    if parsed:
                                        store_data(url, parsed)
                                        total_records += len(parsed)
                                        logger.debug(f"Stored {len(parsed)} records from {zone_name}")
                            except Exception as e:
                                logger.error(f"Error fetching from {zone_name}: {e}")
                                add_sync_log(sync_id, f'خطا در دریافت از {zone_name}: {str(e)[:100]}', 'error')
                        
                        # Update sync status every iteration
                        from .scheduler import get_scheduler_app_context
                        with get_scheduler_app_context():
                            sync_obj = DataSync.query.get(sync_id)
                            if sync_obj:
                                sync_obj.last_sync_at = datetime.utcnow()
                                sync_obj.records_synced = total_records
                                sync_obj.status = 'running'
                                db.session.commit()
                        
                        # Update progress
                        update_sync_progress(
                            sync_id,
                            status='running',
                            progress=50,
                            records_processed=total_records,
                            current_step=f'همگام‌سازی مداوم - دور {iteration}: {total_records} رکورد دریافت شد'
                        )
                        
                        if iteration == 1:
                            add_sync_log(sync_id, f'اولین دور همگام‌سازی انجام شد: {total_records} رکورد', 'success')
                        
                        # Sleep for interval
                        time.sleep(FETCH_INTERVAL)
                        
                    except Exception as e:
                        logger.error(f"Error in LMS continuous sync iteration: {e}", exc_info=True)
                        add_sync_log(sync_id, f'خطا در دور همگام‌سازی: {str(e)[:100]}', 'error')
                        time.sleep(60)  # Wait 1 minute before retrying
                        
            except Exception as e:
                logger.error(f"Fatal error in LMS continuous sync: {e}", exc_info=True)
                update_sync_progress(sync_id, status='failed', progress=0, current_step=f'خطا: {str(e)[:100]}')
                add_sync_log(sync_id, f'خطای مهلک در همگام‌سازی مداوم: {str(e)}', 'error')
                
                from .scheduler import get_scheduler_app_context
                with get_scheduler_app_context():
                    sync_obj = DataSync.query.get(sync_id)
                    if sync_obj:
                        sync_obj.status = 'failed'
                        sync_obj.error_message = str(e)[:500]
                        db.session.commit()
            finally:
                _lms_continuous_running = False
                logger.info("LMS continuous sync stopped")
        
        # Start continuous sync thread
        _lms_continuous_thread = threading.Thread(target=continuous_lms_sync, daemon=True)
        _lms_continuous_thread.start()
        
        update_sync_progress(sync_id, status='running', current_step='همگام‌سازی مداوم شروع شد...', progress=20)
        add_sync_log(sync_id, 'همگام‌سازی مداوم LMS شروع شد', 'info')
        
        return True, 0, None
    
    # Manual sync - use lms_sync.py for one-time sync
    if manual_sync or not sync.auto_sync_enabled:
        try:
            # Initialize progress tracking
            update_sync_progress(sync_id, status='running', current_step='شروع همگام‌سازی دستی...', progress=0)
            add_sync_log(sync_id, 'شروع همگام‌سازی دستی داده‌های LMS', 'info')
            
            # Update sync status
            sync.status = 'running'
            sync.last_synced_by = user_id
            db.session.commit()
            
            start_time = datetime.utcnow()
            
            # Import LMS sync module
            import sys
            lms_module_path = os.path.join(FETCH_DATA_DIR, 'lms_sync.py')
            if not os.path.exists(lms_module_path):
                raise FileNotFoundError(f"LMS sync module not found: {lms_module_path}")
            
            update_sync_progress(sync_id, current_step='در حال دریافت داده از API...', progress=20)
            add_sync_log(sync_id, 'در حال دریافت داده از سرورهای LMS', 'info')
            
            # Execute LMS sync
            cmd = [sys.executable, lms_module_path]
            
            process = subprocess.Popen(
                cmd,
                cwd=FETCH_DATA_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            output_lines = []
            records_count = 0
            
            def monitor_output():
                nonlocal records_count
                try:
                    for line in process.stdout:
                        output_lines.append(line)
                        line = line.strip()
                        
                        if '[INFO]' in line:
                            add_sync_log(sync_id, line.replace('[INFO]', '').strip(), 'info')
                            # Check for record count
                            if 'Stored' in line and 'records' in line:
                                try:
                                    parts = line.split()
                                    for i, part in enumerate(parts):
                                        if part.isdigit() and i < len(parts) - 1 and 'records' in parts[i+1]:
                                            records_count = int(part)
                                            break
                                except:
                                    pass
                        elif '[ERROR]' in line or '[WARNING]' in line:
                            add_sync_log(sync_id, line.replace('[ERROR]', '').replace('[WARNING]', '').strip(), 'error')
                        elif 'Total records' in line:
                            try:
                                parts = line.split('Total records:')
                                if len(parts) > 1:
                                    records_count = int(parts[1].strip())
                            except:
                                pass
                except Exception as e:
                    logger.error(f"Error monitoring LMS output: {e}")
            
            monitor_thread = threading.Thread(target=monitor_output, daemon=True)
            monitor_thread.start()
            
            try:
                process.wait(timeout=1800)  # 30 minutes timeout
                result_code = process.returncode
                stderr_output = process.stderr.read() if process.stderr else ''
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise subprocess.TimeoutExpired(process.args, 1800)
            
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            if result_code == 0:
                # Get actual record count from database if available
                if records_count == 0:
                    try:
                        import sqlite3
                        db_path = os.path.join(FETCH_DATA_DIR, 'faculty_data.db')
                        if os.path.exists(db_path):
                            conn = sqlite3.connect(db_path)
                            cursor = conn.cursor()
                            cursor.execute("SELECT COUNT(*) FROM monitor_data WHERE timestamp > datetime('now', '-1 hour')")
                            records_count = cursor.fetchone()[0]
                            conn.close()
                    except:
                        pass
                
                update_sync_progress(
                    sync_id,
                    status='success',
                    progress=100,
                    records_processed=records_count,
                    current_step=f'همگام‌سازی با موفقیت انجام شد: {records_count} رکورد'
                )
                add_sync_log(sync_id, f'همگام‌سازی با موفقیت انجام شد. تعداد رکوردها: {records_count}', 'success')
                
                sync.status = 'success'
                sync.last_sync_at = end_time
                sync.records_synced = records_count
                sync.sync_duration_seconds = duration
                sync.error_message = None
                
                db.session.commit()
                logger.info(f"LMS sync completed successfully: {records_count} records in {duration:.2f}s")
                
                threading.Timer(300, clear_sync_progress, args=[sync_id]).start()
                
                # If auto_sync was running before manual sync, restart it
                if auto_sync_was_running and sync.auto_sync_enabled:
                    logger.info("Restarting continuous sync after manual sync")
                    # Use a short delay to ensure manual sync is fully complete
                    def restart_continuous_sync():
                        import time
                        time.sleep(2)
                        try:
                            from .scheduler import get_scheduler_app_context
                            with get_scheduler_app_context():
                                run_lms_sync(user_id=user_id, sync_id=sync_id, manual_sync=False)
                        except Exception as e:
                            logger.error(f"Error restarting continuous sync: {e}")
                    
                    threading.Thread(target=restart_continuous_sync, daemon=True).start()
                
                return True, records_count, None
                
            else:
                error_msg = stderr_output or '\n'.join(output_lines) or "Unknown error"
                update_sync_progress(sync_id, status='failed', progress=0, current_step='خطا در همگام‌سازی')
                add_sync_log(sync_id, f'خطا: {error_msg[:200]}', 'error')
                
                sync.status = 'failed'
                sync.error_message = error_msg[:500]
                sync.sync_duration_seconds = duration
                db.session.commit()
                logger.error(f"LMS sync failed: {error_msg}")
                
                threading.Timer(300, clear_sync_progress, args=[sync_id]).start()
                return False, 0, error_msg
                
        except subprocess.TimeoutExpired:
            update_sync_progress(sync_id, status='failed', progress=0, current_step='Timeout: همگام‌سازی بیش از 30 دقیقه طول کشید')
            add_sync_log(sync_id, 'خطا: همگام‌سازی بیش از 30 دقیقه طول کشید', 'error')
            
            sync.status = 'failed'
            sync.error_message = "Sync timeout after 30 minutes"
            db.session.commit()
            logger.error("LMS sync timeout")
            
            threading.Timer(300, clear_sync_progress, args=[sync_id]).start()
            return False, 0, "Sync timeout after 30 minutes"
            
        except Exception as e:
            error_msg = str(e)
            update_sync_progress(sync_id, status='failed', progress=0, current_step=f'خطا: {error_msg[:100]}')
            add_sync_log(sync_id, f'خطا: {error_msg}', 'error')
            
            sync.status = 'failed'
            sync.error_message = error_msg[:500]
            db.session.commit()
            logger.error(f"LMS sync error: {error_msg}", exc_info=True)
            
            threading.Timer(300, clear_sync_progress, args=[sync_id]).start()
            return False, 0, error_msg


def stop_sync_by_source(data_source, sync_id=None):
    """
    Stop sync for a specific data source
    Returns: (success: bool, message: str)
    """
    if data_source == 'lms':
        return stop_lms_continuous_sync()
    else:
        # For other syncs, just update status
        try:
            sync = DataSync.query.filter_by(data_source=data_source).first() if not sync_id else DataSync.query.get(sync_id)
            if not sync:
                return False, "Sync configuration not found"
            
            if sync.status != 'running':
                return False, "Sync در حال اجرا نیست"
            
            sync.status = 'stopped'
            db.session.commit()
            logger.info(f"Sync {data_source} stopped")
            return True, "Sync متوقف شد"
        except Exception as e:
            logger.error(f"Error stopping sync {data_source}: {e}", exc_info=True)
            return False, f"خطا در توقف sync: {str(e)}"

def run_sync_by_source(data_source, user_id=None, sync_id=None):
    """
    Run sync for a specific data source
    """
    if data_source == 'faculty':
        return run_faculty_sync(user_id, sync_id)
    elif data_source == 'students':
        return run_students_sync(user_id, sync_id)
    elif data_source == 'lms':
        return run_lms_sync(user_id, sync_id)
    else:
        return False, 0, f"Unknown data source: {data_source}"
