import eventlet
eventlet.monkey_patch()

import os
from flask import Flask
from config import config
from extensions import db, login_manager, socketio


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    login_manager.init_app(app)
    socketio.init_app(
        app,
        cors_allowed_origins='*',
        message_queue=app.config.get('REDIS_URL'),
        async_mode='eventlet',
    )

    @app.after_request
    def add_security_headers(response):
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "connect-src 'self' ws: wss:;"           # 允許 WebSocket 連線
        )
        return response

    from routes.auth import auth_bp
    from routes.host import host_bp
    from routes.player import player_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(host_bp, url_prefix='/host')
    app.register_blueprint(player_bp, url_prefix='/')

    import sockets.game  # noqa: F401 — registers socket event handlers

    with app.app_context():
        db.create_all()

    return app


app = create_app()

if __name__ == '__main__':
    debug = os.environ.get('FLASK_ENV', 'development') != 'production'
    socketio.run(app, host='0.0.0.0', port=5000, debug=debug)
