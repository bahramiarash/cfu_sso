"""
User Context and Access Level Management
Manages user's organizational context and data access permissions
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from flask import session
from models import User, AccessLevel as AccessLevelModel
import logging

logger = logging.getLogger(__name__)


class AccessLevel(Enum):
    """User access levels in the organization"""
    CENTRAL_ORG = "central_org"      # سازمان مرکزی - دسترسی به همه داده‌ها
    PROVINCE_UNIVERSITY = "province_university"  # دانشگاه استان - فقط داده‌های استان
    FACULTY = "faculty"               # دانشکده - فقط داده‌های دانشکده
    ADMIN = "admin"                   # مدیر سیستم - دسترسی کامل


class UserContext:
    """
    Represents user's organizational context and access permissions
    Determines what data the user can see based on their role and location
    """
    
    def __init__(self, user: User, user_info: Optional[Dict] = None):
        self.user = user
        self.user_info = user_info or {}
        self.logger = logging.getLogger(f"context.{user.sso_id}")
        
        # Extract organizational information from user or session
        self.province_code = self._get_province_code()
        self.university_code = self._get_university_code()
        self.faculty_code = self._get_faculty_code()
        self.access_level = self._determine_access_level()
        
        # Data access filters
        self.data_filters = self._build_data_filters()
    
    def _get_province_code(self) -> Optional[int]:
        """Get user's province code from user model or session"""
        # Check if user model has province_code field
        if hasattr(self.user, 'province_code') and self.user.province_code:
            return self.user.province_code
        
        # Check session
        user_info = session.get('user_info', {})
        return user_info.get('province_code') or user_info.get('provinceCode')
    
    def _get_university_code(self) -> Optional[int]:
        """Get user's university code"""
        if hasattr(self.user, 'university_code') and self.user.university_code:
            return self.user.university_code
        
        user_info = session.get('user_info', {})
        return user_info.get('university_code') or user_info.get('universityCode')
    
    def _get_faculty_code(self) -> Optional[int]:
        """Get user's faculty code"""
        if hasattr(self.user, 'faculty_code') and self.user.faculty_code:
            return self.user.faculty_code
        
        user_info = session.get('user_info', {})
        return user_info.get('faculty_code') or user_info.get('facultyCode') or user_info.get('code_markaz')
    
    def _determine_access_level(self) -> AccessLevel:
        """Determine user's access level based on role and organizational position"""
        # Check if user is admin
        if self.user.is_admin():
            return AccessLevel.ADMIN
        
        # Check access levels from database
        access_levels = [acc.level.lower() for acc in self.user.access_levels]
        
        if 'central_org' in access_levels or 'central' in access_levels:
            return AccessLevel.CENTRAL_ORG
        
        if 'province_university' in access_levels or 'province' in access_levels:
            return AccessLevel.PROVINCE_UNIVERSITY
        
        if 'faculty' in access_levels:
            return AccessLevel.FACULTY
        
        # Default: determine by organizational position
        if self.faculty_code:
            return AccessLevel.FACULTY
        elif self.university_code or self.province_code:
            return AccessLevel.PROVINCE_UNIVERSITY
        else:
            # Default to central org if no specific location
            return AccessLevel.CENTRAL_ORG
    
    def _build_data_filters(self) -> Dict[str, Any]:
        """Build data filters based on user's access level"""
        filters = {
            'access_level': self.access_level,
            'can_filter_by_province': False,
            'can_filter_by_university': False,
            'can_filter_by_faculty': False,
            'province_code': None,
            'university_code': None,
            'faculty_code': None,
        }
        
        if self.access_level == AccessLevel.CENTRAL_ORG or self.access_level == AccessLevel.ADMIN:
            # Central org can see all data and filter by province/university/faculty
            filters['can_filter_by_province'] = True
            filters['can_filter_by_university'] = True
            filters['can_filter_by_faculty'] = True
            # No default filters - can see everything
        
        elif self.access_level == AccessLevel.PROVINCE_UNIVERSITY:
            # Province university can only see their province data
            filters['province_code'] = self.province_code
            filters['can_filter_by_university'] = True
            filters['can_filter_by_faculty'] = True
        
        elif self.access_level == AccessLevel.FACULTY:
            # Faculty can only see their faculty data
            filters['faculty_code'] = self.faculty_code
            filters['province_code'] = self.province_code  # For reference
        
        return filters
    
    def can_access_province(self, province_code: Optional[int]) -> bool:
        """Check if user can access data for a specific province"""
        if self.access_level in [AccessLevel.CENTRAL_ORG, AccessLevel.ADMIN]:
            return True
        
        if self.access_level == AccessLevel.PROVINCE_UNIVERSITY:
            return province_code == self.province_code
        
        if self.access_level == AccessLevel.FACULTY:
            return province_code == self.province_code
        
        return False
    
    def can_access_faculty(self, faculty_code: Optional[int]) -> bool:
        """Check if user can access data for a specific faculty"""
        if self.access_level in [AccessLevel.CENTRAL_ORG, AccessLevel.ADMIN]:
            return True
        
        if self.access_level == AccessLevel.PROVINCE_UNIVERSITY:
            # Can access if in same province
            return True  # Will be filtered by province_code
        
        if self.access_level == AccessLevel.FACULTY:
            return faculty_code == self.faculty_code
        
        return False
    
    def apply_filters(self, query_filters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply user's access filters to query filters
        Merges user's access restrictions with requested filters
        """
        result = query_filters.copy()
        
        # Apply access level restrictions
        if self.data_filters['province_code']:
            result['province_code'] = self.data_filters['province_code']
        
        if self.data_filters['faculty_code']:
            result['faculty_code'] = self.data_filters['faculty_code']
        
        if self.data_filters['university_code']:
            result['university_code'] = self.data_filters['university_code']
        
        return result
    
    def get_available_provinces(self) -> List[int]:
        """Get list of province codes user can access"""
        if self.access_level in [AccessLevel.CENTRAL_ORG, AccessLevel.ADMIN]:
            # Can access all provinces - return None means all
            return []
        
        if self.province_code:
            return [self.province_code]
        
        return []
    
    def get_available_faculties(self) -> List[int]:
        """Get list of faculty codes user can access"""
        if self.access_level in [AccessLevel.CENTRAL_ORG, AccessLevel.ADMIN]:
            return []  # All
        
        if self.access_level == AccessLevel.FACULTY and self.faculty_code:
            return [self.faculty_code]
        
        return []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary for template rendering"""
        return {
            'access_level': self.access_level.value,
            'province_code': self.province_code,
            'university_code': self.university_code,
            'faculty_code': self.faculty_code,
            'can_filter_by_province': self.data_filters['can_filter_by_province'],
            'can_filter_by_university': self.data_filters['can_filter_by_university'],
            'can_filter_by_faculty': self.data_filters['can_filter_by_faculty'],
        }


def get_user_context(user: Optional[User] = None) -> UserContext:
    """Get user context from current session"""
    from flask_login import current_user
    
    if user is None:
        user = current_user
    
    if not user or not user.is_authenticated:
        raise ValueError("User is not authenticated")
    
    user_info = session.get('user_info', {})
    return UserContext(user, user_info)


