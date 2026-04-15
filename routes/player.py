import re

from flask import Blueprint, redirect, render_template, request, session, url_for

from extensions import db
from models import GameSession, Player

player_bp = Blueprint('player', __name__)


@player_bp.route('/')
def index():
    return render_template('player/join.html')


@player_bp.route('/join', methods=['POST'])
def join():
    code = request.form.get('code', '').strip().upper()
    nickname = request.form.get('nickname', '').strip()

    if not code or not nickname:
        return render_template('player/join.html', error='請填寫房間代碼和暱稱')

    if not re.match(r'^[\w\s\-_.]{1,20}$', nickname):
        return render_template('player/join.html', error='暱稱只能包含中英文、數字、空格及 - _ . 符號，且不超過 20 字')

    game_session = GameSession.query.filter_by(code=code, status='waiting').first()
    if not game_session:
        return render_template('player/join.html', error='找不到此房間，或競賽已開始 / 結束')

    if Player.query.filter_by(session_id=game_session.id, nickname=nickname).first():
        return render_template('player/join.html', error='此暱稱已被使用，請換一個')

    player = Player(session_id=game_session.id, nickname=nickname)
    db.session.add(player)
    db.session.commit()

    session['player_id'] = player.id
    session['session_code'] = code

    return redirect(url_for('player.lobby', code=code))


@player_bp.route('/lobby/<code>')
def lobby(code):
    player_id = session.get('player_id')
    if not player_id:
        return redirect(url_for('player.index'))

    player = db.session.get(Player, player_id)
    if not player:
        return redirect(url_for('player.index'))

    game_session = GameSession.query.filter_by(code=code).first_or_404()

    if game_session.status == 'ended':
        return redirect(url_for('player.result', code=code))

    return render_template('player/lobby.html', game_session=game_session, player=player)


@player_bp.route('/result/<code>')
def result(code):
    game_session = GameSession.query.filter_by(code=code).first_or_404()
    players = game_session.players.order_by(Player.score.desc()).all()
    players
    return render_template('player/result.html', game_session=game_session, players=players)
