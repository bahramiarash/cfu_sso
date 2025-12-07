"""
Auto Sync Scheduler
Handles automatic scheduled data synchronization
"""
import threading
import time
import logging
from datetime import datetime, timedelta
from extensions import db
from admin_models import DataSync, AccessLog
from models import User
from .sync_handlers import run_sync_by_source

logger = logging.getLogger(__name__)

_scheduler_thread = None
_scheduler_running = False


def get_scheduler_app_context():
    """Get Flask app context for scheduler"""
    # Import app to get context
    try:
        from flask import current_app
        return current_app.app_context()
    except:
        # Fallback if not in request context
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from app import app
        return app.app_context()


def check_and_run_scheduled_syncs():
    """Check for syncs that need to run and execute them"""
    try:
        with get_scheduler_app_context():
            # First, check and restart LMS continuous sync if needed (only if not manually stopped)
            from .sync_handlers import check_and_restart_lms_continuous_sync
            lms_sync = DataSync.query.filter_by(data_source='lms').first()
            if lms_sync and lms_sync.auto_sync_enabled and lms_sync.status != 'stopped':
                check_and_restart_lms_continuous_sync()
            
            now = datetime.utcnow()
            
            # For LMS sync, check if it's enabled and not running (continuous sync)
            # For other syncs, check next_sync_at
            # Don't auto-start syncs that are manually stopped
            from sqlalchemy import or_, and_
            due_syncs = DataSync.query.filter(
                DataSync.auto_sync_enabled == True,
                DataSync.status != 'running',
                DataSync.status != 'stopped',  # Don't auto-start manually stopped syncs
                or_(
                    # LMS sync: start if not running (continuous mode) and next_sync_at is None or past
                    and_(
                        DataSync.data_source == 'lms',
                        or_(
                            DataSync.next_sync_at.is_(None),
                            DataSync.next_sync_at <= now
                        )
                    ),
                    # Other syncs: check next_sync_at
                    and_(
                        DataSync.data_source != 'lms',
                        DataSync.next_sync_at <= now
                    )
                )
            ).all()
            
            for sync in due_syncs:
                logger.info(f"Auto-sync triggered for {sync.data_source} (ID: {sync.id})")
                
                # Run sync in background thread
                def run_sync(sync_id, data_source):
                    try:
                        with get_scheduler_app_context():
                            # Get sync again to ensure we have latest data
                            sync_obj = DataSync.query.get(sync_id)
                            if not sync_obj:
                                return
                            
                            # Get system user ID (first admin user or None)
                            system_user_id = None
                            try:
                                system_user = User.query.filter_by(access_level='CENTRAL_ORG').first()
                                if system_user:
                                    system_user_id = system_user.id
                            except:
                                pass
                            
                            # Log the auto-sync start
                            from .utils import log_action
                            log_action('auto_sync_started', 'data_sync', sync_id, {
                                'data_source': data_source,
                                'scheduled_at': sync_obj.next_sync_at.isoformat() if sync_obj.next_sync_at else None
                            }, user_id=system_user_id)
                            
                            # Run the sync
                            from .sync_handlers import run_sync_by_source
                            success, records_count, error_message = run_sync_by_source(
                                data_source, 
                                user_id=system_user_id,  # System user for auto-sync
                                sync_id=sync_id
                            )
                            
                            # Log the result
                            log_action(
                                'auto_sync_completed' if success else 'auto_sync_failed',
                                'data_sync',
                                sync_id,
                                {
                                    'data_source': data_source,
                                    'success': success,
                                    'records_count': records_count,
                                    'error_message': error_message
                                },
                                user_id=system_user_id
                            )
                            
                    except Exception as e:
                        logger.error(f"Error in auto-sync thread for {data_source}: {e}", exc_info=True)
                        # Log the error
                        try:
                            with get_scheduler_app_context():
                                from .utils import log_action
                                system_user_id = None
                                try:
                                    system_user = User.query.filter_by(access_level='CENTRAL_ORG').first()
                                    if system_user:
                                        system_user_id = system_user.id
                                except:
                                    pass
                                log_action('auto_sync_error', 'data_sync', sync_id, {
                                    'data_source': data_source,
                                    'error': str(e)
                                }, user_id=system_user_id)
                        except:
                            pass
                
                # Start sync in background thread
                thread = threading.Thread(
                    target=run_sync,
                    args=(sync.id, sync.data_source),
                    daemon=True
                )
                thread.start()
                
    except Exception as e:
        logger.error(f"Error in scheduler: {e}", exc_info=True)


def scheduler_loop():
    """Main scheduler loop"""
    global _scheduler_running
    _scheduler_running = True
    logger.info("Auto-sync scheduler started")
    
    while _scheduler_running:
        try:
            check_and_run_scheduled_syncs()
        except Exception as e:
            logger.error(f"Error in scheduler loop: {e}", exc_info=True)
        
        # Check every minute
        time.sleep(60)
    
    logger.info("Auto-sync scheduler stopped")


def start_scheduler():
    """Start the auto-sync scheduler"""
    global _scheduler_thread, _scheduler_running
    
    if _scheduler_thread and _scheduler_thread.is_alive():
        logger.warning("Scheduler already running")
        return
    
    _scheduler_running = True
    _scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
    _scheduler_thread.start()
    logger.info("Auto-sync scheduler thread started")


def stop_scheduler():
    """Stop the auto-sync scheduler"""
    global _scheduler_running
    _scheduler_running = False
    logger.info("Auto-sync scheduler stop requested")


def is_scheduler_running():
    """Check if scheduler is running"""
    return _scheduler_running and _scheduler_thread and _scheduler_thread.is_alive()
