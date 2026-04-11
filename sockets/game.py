from datetime import datetime

from flask import request
from flask_socketio import emit, join_room

from extensions import db, socketio
from models import Choice, GameSession, Player, PlayerAnswer, Question


# ── Connection ──────────────────────────────────────────────────────────────

@socketio.on('connect')
def on_connect():
    pass


# ── Host events ─────────────────────────────────────────────────────────────

@socketio.on('host_join')
def on_host_join(data):
    session_id = data.get('session_id')
    game_session = db.session.get(GameSession, session_id)
    if not game_session:
        return

    join_room(f'game_{game_session.code}')
    join_room(f'host_{game_session.code}')

    players = [p.nickname for p in game_session.players]
    emit('host_connected', {
        'code': game_session.code,
        'player_count': len(players),
        'players': players,
        'status': game_session.status,
    })


@socketio.on('start_game')
def on_start_game(data):
    session_id = data.get('session_id')
    game_session = db.session.get(GameSession, session_id)
    if not game_session or game_session.status != 'waiting':
        return

    game_session.status = 'active'
    game_session.started_at = datetime.utcnow()
    db.session.commit()

    emit('game_started', {}, to=f'game_{game_session.code}')


@socketio.on('next_question')
def on_next_question(data):
    session_id = data.get('session_id')
    game_session = db.session.get(GameSession, session_id)
    if not game_session or game_session.status != 'active':
        return

    questions = game_session.quiz.questions.order_by(Question.order).all()
    next_index = game_session.current_question_index + 1

    if next_index >= len(questions):
        _end_game(game_session)
        return

    game_session.current_question_index = next_index
    db.session.commit()

    question = questions[next_index]

    # Players receive question WITHOUT correct answer
    emit('question_start', {
        'question': question.to_dict(include_answer=False),
        'question_number': next_index + 1,
        'total_questions': len(questions),
    }, to=f'game_{game_session.code}')

    # Host receives WITH correct answer marked
    emit('question_start_host', {
        'question': question.to_dict(include_answer=True),
        'question_number': next_index + 1,
        'total_questions': len(questions),
    }, to=f'host_{game_session.code}')


@socketio.on('end_question')
def on_end_question(data):
    session_id = data.get('session_id')
    game_session = db.session.get(GameSession, session_id)
    if not game_session or game_session.status != 'active':
        return
    if game_session.current_question_index < 0:
        return

    questions = game_session.quiz.questions.order_by(Question.order).all()
    current_question = questions[game_session.current_question_index]

    correct_choice = current_question.choices.filter_by(is_correct=True).first()

    choices_stats = []
    for choice in current_question.choices:
        count = PlayerAnswer.query.filter_by(
            question_id=current_question.id, choice_id=choice.id
        ).count()
        choices_stats.append({
            'id': choice.id,
            'text': choice.text,
            'is_correct': choice.is_correct,
            'count': count,
        })

    leaderboard = _get_leaderboard(game_session, limit=5)

    emit('question_ended', {
        'correct_choice_id': correct_choice.id if correct_choice else None,
        'choices_stats': choices_stats,
        'leaderboard': leaderboard,
    }, to=f'game_{game_session.code}')


@socketio.on('end_game')
def on_end_game(data):
    session_id = data.get('session_id')
    game_session = db.session.get(GameSession, session_id)
    if game_session:
        _end_game(game_session)


# ── Player events ────────────────────────────────────────────────────────────

@socketio.on('player_join')
def on_player_join(data):
    code = data.get('code')
    player_id = data.get('player_id')

    game_session = GameSession.query.filter_by(code=code).first()
    player = db.session.get(Player, player_id)

    if not game_session or not player:
        return

    player.socket_id = request.sid
    db.session.commit()

    join_room(f'game_{code}')

    emit('player_joined', {
        'nickname': player.nickname,
        'player_count': game_session.players.count(),
    }, to=f'host_{code}')


@socketio.on('submit_answer')
def on_submit_answer(data):
    player_id = data.get('player_id')
    choice_id = data.get('choice_id')
    response_time_ms = int(data.get('response_time_ms', 0))

    player = db.session.get(Player, player_id)
    if not player:
        return

    game_session = player.session
    if game_session.status != 'active' or game_session.current_question_index < 0:
        return

    questions = game_session.quiz.questions.order_by(Question.order).all()
    current_question = questions[game_session.current_question_index]

    # Prevent double-answer
    if PlayerAnswer.query.filter_by(player_id=player_id, question_id=current_question.id).first():
        return

    choice = db.session.get(Choice, choice_id) if choice_id else None
    points = 0

    if choice and choice.is_correct:
        time_limit_ms = current_question.time_limit * 1000
        time_ratio = min(response_time_ms / max(time_limit_ms, 1), 1.0)
        points = int(1000 * (1 - time_ratio * 0.5))  # 500–1000 points depending on speed

    answer = PlayerAnswer(
        player_id=player_id,
        question_id=current_question.id,
        choice_id=choice_id,
        response_time_ms=response_time_ms,
        points_earned=points,
    )
    player.score += points
    db.session.add(answer)
    db.session.commit()

    answered_count = PlayerAnswer.query.filter_by(question_id=current_question.id).count()
    total_players = game_session.players.count()

    emit('answer_received', {
        'answered': answered_count,
        'total': total_players,
    }, to=f'host_{game_session.code}')

    emit('answer_confirmed', {'points': points}, to=request.sid)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_leaderboard(game_session, limit=None):
    q = game_session.players.order_by(Player.score.desc())
    if limit:
        q = q.limit(limit)
    return [{'nickname': p.nickname, 'score': p.score} for p in q]


def _end_game(game_session):
    game_session.status = 'ended'
    game_session.ended_at = datetime.utcnow()
    db.session.commit()

    leaderboard = _get_leaderboard(game_session)
    emit('game_ended', {
        'leaderboard': leaderboard,
        'result_url': f'/result/{game_session.code}',
    }, to=f'game_{game_session.code}')
