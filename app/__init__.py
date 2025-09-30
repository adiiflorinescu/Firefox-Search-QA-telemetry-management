# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/__init__.py

import os
from flask import Flask, redirect, url_for, g

def create_app():
    """Create and configure an instance of the Flask application."""
    app = Flask(__name__,
                instance_relative_config=True,
                template_folder=os.path.join(os.path.abspath(os.path.dirname(__file__)), '../templates'),
                static_folder=os.path.join(os.path.abspath(os.path.dirname(__file__)), '../static'))

    # --- Load Configuration ---
    # Load default config from the object
    app.config.from_object('config')
    # Load optional config from the instance folder
    app.config.from_pyfile('config.py', silent=True)

    # Environment variables from .env/.flaskenv are now loaded automatically by Flask.
    # We just need to pull them from os.environ into the app.config.
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-default-secret-key-for-dev-only')
    app.config['DATABASE'] = os.path.join(app.instance_path, 'metrics.db')

    # Ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Initialize database functions (get_db, close_db)
    from . import db
    db.init_app(app)

    # Initialize CLI commands (init-db)
    from . import commands
    commands.register_commands(app)

    # --- Register Blueprints (Routes) ---
    # This order is correct to resolve dependencies.
    from .routes import main
    app.register_blueprint(main.bp)

    from .routes import auth
    app.register_blueprint(auth.bp)

    from .routes import planning
    app.register_blueprint(planning.bp)

    from .routes import management
    app.register_blueprint(management.bp)

    from .routes import user_management
    app.register_blueprint(user_management.bp)


    # Add a default route to redirect to login or metrics
    @app.route('/')
    def index_route():
        if g.user:
            return redirect(url_for('main.metrics'))
        return redirect(url_for('auth.login'))

    # --- Register Custom Template Filters ---
    try:
        from .utils.template_filters import strip_tcid_prefix, sort_details
        app.jinja_env.filters['strip_tcid_prefix'] = strip_tcid_prefix
        app.jinja_env.filters['sort_details'] = sort_details
    except ImportError:
        pass

    return app