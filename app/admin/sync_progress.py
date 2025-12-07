"""
Sync Progress Tracking
Tracks real-time progress of data synchronization
"""
import threading
import time
import logging
from datetime import datetime
from typing import Dict, Optional
from extensions import db
from admin_models import DataSync

logger = logging.getLogger(__name__)

# In-memory progress tracking (for real-time updates)
# Format: {sync_id: {'status': 'running', 'progress': 0-100, 'current_step': str, 'records_processed': int, 'total_records': int, 'logs': []}}
_sync_progress: Dict[int, Dict] = {}
_progress_lock = threading.Lock()


def get_sync_progress(sync_id: int) -> Optional[Dict]:
    """Get current progress for a sync operation"""
    with _progress_lock:
        return _sync_progress.get(sync_id, None)


def update_sync_progress(sync_id: int, **kwargs):
    """Update progress for a sync operation"""
    with _progress_lock:
        if sync_id not in _sync_progress:
            _sync_progress[sync_id] = {
                'status': 'running',
                'progress': 0,
                'current_step': '',
                'records_processed': 0,
                'total_records': 0,
                'logs': [],
                'start_time': datetime.utcnow().isoformat()
            }
        
        _sync_progress[sync_id].update(kwargs)
        
        # Keep only last 100 log entries
        if 'logs' in _sync_progress[sync_id] and len(_sync_progress[sync_id]['logs']) > 100:
            _sync_progress[sync_id]['logs'] = _sync_progress[sync_id]['logs'][-100:]


def add_sync_log(sync_id: int, message: str, level: str = 'info'):
    """Add a log message to sync progress"""
    with _progress_lock:
        if sync_id not in _sync_progress:
            update_sync_progress(sync_id)
        
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': level,
            'message': message
        }
        _sync_progress[sync_id]['logs'].append(log_entry)


def clear_sync_progress(sync_id: int):
    """Clear progress after sync completes"""
    with _progress_lock:
        if sync_id in _sync_progress:
            # Keep final status for a while, then clear
            _sync_progress[sync_id]['status'] = 'completed'
            # Will be cleared after 1 hour by cleanup task


def cleanup_old_progress():
    """Clean up old progress entries (run periodically)"""
    with _progress_lock:
        current_time = datetime.utcnow()
        to_remove = []
        
        for sync_id, progress in _sync_progress.items():
            if progress.get('status') == 'completed':
                start_time = datetime.fromisoformat(progress.get('start_time', current_time.isoformat()))
                if (current_time - start_time).total_seconds() > 3600:  # 1 hour
                    to_remove.append(sync_id)
        
        for sync_id in to_remove:
            del _sync_progress[sync_id]


