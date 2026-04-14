from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import Choice, GameSession, Player, Question, Quiz, generate_room_code

host_bp = Blueprint('host', __name__)


# ── Dashboard ──────────────────────────────────────────────────────────────

@host_bp.route('/dashboard')
@login_required
def dashboard():
    quizzes = current_user.quizzes.order_by(Quiz.created_at.desc()).all()
    return render_template('host/dashboard.html', quizzes=quizzes)


# ── Quiz CRUD ───────────────────────────────────────────────────────────────

@host_bp.route('/quiz/new', methods=['GET', 'POST'])
@login_required
def quiz_new():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        if not title:
            flash('請填寫競賽名稱', 'error')
            return render_template('host/quiz_edit.html', quiz=None, questions=[])
        quiz = Quiz(title=title, description=description, host_id=current_user.id)
        db.session.add(quiz)
        db.session.commit()
        return redirect(url_for('host.quiz_edit', quiz_id=quiz.id))
    return render_template('host/quiz_edit.html', quiz=None, questions=[])


@host_bp.route('/quiz/<int:quiz_id>/edit', methods=['GET', 'POST', 'PUT'])
@login_required
def quiz_edit(quiz_id):
    quiz = Quiz.query.filter_by(id=quiz_id, host_id=current_user.id).first_or_404()
    questions = quiz.questions.all()
    return render_template('host/quiz_edit.html', quiz=quiz, questions=questions)


@host_bp.route('/quiz/<int:quiz_id>/delete', methods=['POST'])
@login_required
def quiz_delete(quiz_id):
    quiz = Quiz.query.filter_by(id=quiz_id, host_id=current_user.id).first_or_404()
    db.session.delete(quiz)
    db.session.commit()
    return redirect(url_for('host.dashboard'))


# ── Question API (JSON) ─────────────────────────────────────────────────────

@host_bp.route('/quiz/<int:quiz_id>/question', methods=['POST'])
@login_required
def question_add(quiz_id):
    quiz = Quiz.query.filter_by(id=quiz_id, host_id=current_user.id).first_or_404()
    data = request.get_json()
    if not data or not data.get('text'):
        return jsonify({'error': '題目不能為空'}), 400

    count = quiz.questions.count()
    question = Question(
        quiz_id=quiz.id,
        text=data['text'],
        time_limit=int(data.get('time_limit', 20)),
        order=count,
    )
    db.session.add(question)
    db.session.flush()

    for choice_data in data.get('choices', []):
        db.session.add(Choice(
            question_id=question.id,
            text=choice_data['text'],
            is_correct=bool(choice_data.get('is_correct', False)),
        ))

    db.session.commit()
    return jsonify(question.to_dict(include_answer=True))


@host_bp.route('/question/<int:question_id>', methods=['PUT'])
@login_required
def question_update(question_id):
    question = Question.query.get_or_404(question_id)
    if question.quiz.host_id != current_user.id:
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json()
    question.text = data.get('text', question.text)
    question.time_limit = int(data.get('time_limit', question.time_limit))

    # Replace choices
    for c in question.choices.all():
        db.session.delete(c)
    db.session.flush()

    for choice_data in data.get('choices', []):
        db.session.add(Choice(
            question_id=question.id,
            text=choice_data['text'],
            is_correct=bool(choice_data.get('is_correct', False)),
        ))

    db.session.commit()
    return jsonify(question.to_dict(include_answer=True))


@host_bp.route('/question/<int:question_id>', methods=['DELETE'])
@login_required
def question_delete(question_id):
    question = Question.query.get_or_404(question_id)
    if question.quiz.host_id != current_user.id:
        return jsonify({'error': 'Forbidden'}), 403
    db.session.delete(question)
    db.session.commit()
    return jsonify({'success': True})


# ── Game Session ────────────────────────────────────────────────────────────

@host_bp.route('/quiz/<int:quiz_id>/launch', methods=['POST'])
@login_required
def game_launch(quiz_id):
    quiz = Quiz.query.filter_by(id=quiz_id, host_id=current_user.id).first_or_404()
    if quiz.questions.count() == 0:
        flash('請先新增至少一道題目', 'error')
        return redirect(url_for('host.quiz_edit', quiz_id=quiz_id))

    code = generate_room_code()
    game_session = GameSession(
        quiz_id=quiz.id,
        host_id=current_user.id,
        code=code,
        status='waiting',
    )
    db.session.add(game_session)
    db.session.commit()
    return redirect(url_for('host.game_control', session_id=game_session.id))


@host_bp.route('/game/<int:session_id>')
@login_required
def game_control(session_id):
    game_session = GameSession.query.filter_by(
        id=session_id, host_id=current_user.id
    ).first_or_404()
    questions = game_session.quiz.questions.all()
    players = game_session.players.order_by(Player.score.desc()).all()
    return render_template(
        'host/game_control.html',
        session=game_session,
        questions=questions,
        players=players,
    )
