import random
import string
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db, login_manager


class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    quizzes = db.relationship('Quiz', backref='host', lazy='dynamic', cascade='all, delete-orphan')
    sessions = db.relationship('GameSession', backref='host', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class Quiz(db.Model):
    __tablename__ = 'quizzes'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text, default='')
    host_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    questions = db.relationship(
        'Question', backref='quiz', lazy='dynamic',
        order_by='Question.order', cascade='all, delete-orphan'
    )
    sessions = db.relationship('GameSession', backref='quiz', lazy='dynamic', cascade='all, delete-orphan')


class Question(db.Model):
    __tablename__ = 'questions'

    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quizzes.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    time_limit = db.Column(db.Integer, default=20)
    order = db.Column(db.Integer, default=0)

    choices = db.relationship(
        'Choice', backref='question', lazy='dynamic',
        cascade='all, delete-orphan'
    )

    def to_dict(self, include_answer=False):
        return {
            'id': self.id,
            'text': self.text,
            'time_limit': self.time_limit,
            'order': self.order,
            'choices': [c.to_dict(include_answer=include_answer) for c in self.choices],
        }


class Choice(db.Model):
    __tablename__ = 'choices'

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    text = db.Column(db.String(256), nullable=False)
    is_correct = db.Column(db.Boolean, default=False)

    def to_dict(self, include_answer=False):
        data = {'id': self.id, 'text': self.text}
        if include_answer:
            data['is_correct'] = self.is_correct
        return data


class GameSession(db.Model):
    __tablename__ = 'game_sessions'

    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quizzes.id'), nullable=False)
    host_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    code = db.Column(db.String(6), unique=True, nullable=False)
    status = db.Column(db.String(20), default='waiting')  # waiting | active | ended
    current_question_index = db.Column(db.Integer, default=-1)
    started_at = db.Column(db.DateTime)
    ended_at = db.Column(db.DateTime)

    players = db.relationship(
        'Player', backref='session', lazy='dynamic',
        cascade='all, delete-orphan'
    )


class Player(db.Model):
    __tablename__ = 'players'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('game_sessions.id'), nullable=False)
    nickname = db.Column(db.String(64), nullable=False)
    score = db.Column(db.Integer, default=0)
    socket_id = db.Column(db.String(128))

    answers = db.relationship(
        'PlayerAnswer', backref='player', lazy='dynamic',
        cascade='all, delete-orphan'
    )


class PlayerAnswer(db.Model):
    __tablename__ = 'player_answers'

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    choice_id = db.Column(db.Integer, db.ForeignKey('choices.id'), nullable=True)
    response_time_ms = db.Column(db.Integer, default=0)
    points_earned = db.Column(db.Integer, default=0)
    answered_at = db.Column(db.DateTime, default=datetime.utcnow)


def generate_room_code():
    """Generate a unique 6-char alphanumeric room code."""
    chars = string.ascii_uppercase + string.digits
    for _ in range(20):
        code = ''.join(random.choices(chars, k=6))
        exists = GameSession.query.filter(
            GameSession.code == code,
            GameSession.status.in_(['waiting', 'active'])
        ).first()
        if not exists:
            return code
    raise RuntimeError('Could not generate a unique room code')
