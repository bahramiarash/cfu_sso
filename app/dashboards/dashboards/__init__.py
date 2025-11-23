# Dashboards package
# Import all dashboards here to register them
from .faculty_stats import FacultyStatsDashboard
from .faculty_map import FacultyMapDashboard
from .pardis_map import PardisMapDashboard
from .student_faculty_ratio import StudentFacultyRatioDashboard
from .lms_monitoring import LMSMonitoringDashboard
from .students_dashboard import StudentsDashboard

__all__ = [
    'FacultyStatsDashboard',
    'FacultyMapDashboard',
    'PardisMapDashboard',
    'StudentFacultyRatioDashboard',
    'LMSMonitoringDashboard',
    'StudentsDashboard'
]

