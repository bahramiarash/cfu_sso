from app import app
from models import db, User, AccessLevel, Project

with app.app_context():
    # Clear previous data
    db.drop_all()
    db.create_all()

    # Create users with valid sso_id
    user1 = User(sso_id='alice_sso_001', name='Alice')
    db.session.add(user1)
    db.session.commit()  # commit so user1 gets an id

    access1 = AccessLevel(level='admin', user_id=user1.id)
    db.session.add(access1)
    db.session.commit()


    # Add access levels
    db.session.add_all([
        AccessLevel(level='admin', user_id=user1.id),
    ])

    # Add projects
    db.session.add_all([
        Project(name='AI Chatbot', user_id=user1.id),
        Project(name='ML Model', user_id=user1.id),
    ])

    db.session.commit()
    print("Dummy data inserted.")
