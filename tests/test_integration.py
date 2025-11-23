"""
Integration tests for dashboard system
"""
import unittest
from flask import Flask
from flask_login import LoginManager
from app import create_app
from models import db, User, AccessLevel
from dashboards.context import get_user_context

class TestDashboardIntegration(unittest.TestCase):
    """Integration tests for dashboards"""
    
    def setUp(self):
        """Set up test environment"""
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
    
    def tearDown(self):
        """Clean up after tests"""
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
    
    def test_dashboard_list_requires_auth(self):
        """Test that dashboard list requires authentication"""
        response = self.client.get('/dashboards/')
        # Should redirect to login or return 401/403
        self.assertIn(response.status_code, [302, 401, 403])
    
    def test_user_context_creation(self):
        """Test UserContext creation from database user"""
        # Create test user
        user = User(
            sso_id='test_user',
            name='Test User',
            email='test@example.com',
            province_code=1
        )
        db.session.add(user)
        
        # Create access level
        access = AccessLevel(level='province_university', user_id=user.id)
        db.session.add(access)
        db.session.commit()
        
        # Test context creation
        context = UserContext(user, {})
        self.assertEqual(context.province_code, 1)
        self.assertEqual(context.access_level.value, 'province_university')

if __name__ == '__main__':
    unittest.main()


