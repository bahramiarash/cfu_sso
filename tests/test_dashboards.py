"""
Unit tests for dashboard system
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
from dashboards.context import UserContext, AccessLevel
from dashboards.base import BaseDashboard
from dashboards.registry import DashboardRegistry
from dashboards.data_providers.faculty import FacultyDataProvider
from models import User

class TestUserContext(unittest.TestCase):
    """Test UserContext class"""
    
    def setUp(self):
        self.user = Mock(spec=User)
        self.user.sso_id = "test_user"
        self.user.access_levels = []
        self.user.is_admin = Mock(return_value=False)
    
    def test_central_org_access_level(self):
        """Test CENTRAL_ORG access level"""
        access_level = Mock()
        access_level.level = "central_org"
        self.user.access_levels = [access_level]
        
        context = UserContext(self.user, {})
        self.assertEqual(context.access_level, AccessLevel.CENTRAL_ORG)
        self.assertTrue(context.data_filters['can_filter_by_province'])
    
    def test_province_university_access_level(self):
        """Test PROVINCE_UNIVERSITY access level"""
        access_level = Mock()
        access_level.level = "province_university"
        self.user.access_levels = [access_level]
        self.user.province_code = 1
        
        context = UserContext(self.user, {})
        self.assertEqual(context.access_level, AccessLevel.PROVINCE_UNIVERSITY)
        self.assertEqual(context.data_filters['province_code'], 1)
        self.assertFalse(context.data_filters['can_filter_by_province'])
    
    def test_faculty_access_level(self):
        """Test FACULTY access level"""
        access_level = Mock()
        access_level.level = "faculty"
        self.user.access_levels = [access_level]
        self.user.faculty_code = 1001
        self.user.province_code = 1
        
        context = UserContext(self.user, {})
        self.assertEqual(context.access_level, AccessLevel.FACULTY)
        self.assertEqual(context.data_filters['faculty_code'], 1001)
    
    def test_apply_filters(self):
        """Test filter application"""
        context = UserContext(self.user, {})
        context.data_filters['province_code'] = 1
        
        query_filters = {'date_from': '2024-01-01'}
        result = context.apply_filters(query_filters)
        
        self.assertEqual(result['province_code'], 1)
        self.assertEqual(result['date_from'], '2024-01-01')

class TestFacultyDataProvider(unittest.TestCase):
    """Test FacultyDataProvider"""
    
    @patch('dashboards.data_providers.faculty.sqlite3')
    def test_get_faculty_by_sex(self, mock_sqlite3):
        """Test get_faculty_by_sex method"""
        # Mock database connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [('مرد', 100), ('زن', 50)]
        mock_sqlite3.connect.return_value = mock_conn
        
        provider = FacultyDataProvider()
        result = provider.get_faculty_by_sex()
        
        self.assertEqual(result['labels'], ['مرد', 'زن'])
        self.assertEqual(result['counts'], [100, 50])

class TestDashboardRegistry(unittest.TestCase):
    """Test DashboardRegistry"""
    
    def test_register_dashboard(self):
        """Test dashboard registration"""
        class TestDashboard(BaseDashboard):
            def get_data(self, context, **kwargs):
                return {}
            def render(self, data, context):
                return None
        
        DashboardRegistry.register(TestDashboard)
        self.assertTrue(DashboardRegistry.exists('test_dashboard'))
    
    def test_get_dashboard(self):
        """Test getting dashboard from registry"""
        dashboard = DashboardRegistry.get('d1')
        self.assertIsNotNone(dashboard)
        self.assertEqual(dashboard.dashboard_id, 'd1')

if __name__ == '__main__':
    unittest.main()


