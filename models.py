from extensions import db
from flask_login import current_user
from flask import session

from extensions import db
from flask_login import current_user
from flask import session

class User(db.Model):
    __tablename__ = 'user'
    __table_args__ = {'extend_existing': True}
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    # existing fields...
    assistant_id = db.Column(db.String(100), nullable=True)
    instructions = db.Column(db.String(500))
    botName = db.Column(db.String(100))
    thread_id = db.Column(db.String(100), nullable=True)

    @staticmethod
    def get_assistant_info():
        username = session.get('username')
        user = User.query.filter_by(username=username).first()
        if user:
            return user.assistant_id, user.instructions, user.botName
        else:
            return None, None, None