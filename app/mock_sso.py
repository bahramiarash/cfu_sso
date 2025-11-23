"""
Mock SSO for local testing
Only use this in development mode
"""
from flask import session, redirect, url_for, request
from models import User, AccessLevel, db
from flask_login import login_user

def mock_sso_login(username, access_level='central_org', province_code=None, faculty_code=None):
    """
    Mock SSO login for testing
    Usage: /mock_login?username=test_central&access_level=central_org
    """
    # Find or create user
    user = User.query.filter_by(sso_id=username).first()
    if not user:
        user = User(
            sso_id=username,
            name=f'Test User {username}',
            email=f'{username}@test.com',
            province_code=province_code,
            faculty_code=faculty_code
        )
        db.session.add(user)
        db.session.flush()
    else:
        # Update user info if provided
        if province_code is not None:
            user.province_code = province_code
        if faculty_code is not None:
            user.faculty_code = faculty_code
        db.session.flush()
    
    # Set access level
    existing_access = AccessLevel.query.filter_by(user_id=user.id, level=access_level).first()
    if not existing_access:
        # Remove old access levels
        AccessLevel.query.filter_by(user_id=user.id).delete()
        # Add new access level
        access = AccessLevel(level=access_level, user_id=user.id)
        db.session.add(access)
    
    db.session.commit()
    
    # Set session
    session['user_info'] = {
        'username': username,
        'fullname': user.name,
        'usertype': access_level,
        'province_code': province_code,
        'faculty_code': faculty_code
    }
    session['access_level'] = [access_level]
    
    login_user(user)
    
    return redirect(url_for('dashboard.dashboard_list'))


