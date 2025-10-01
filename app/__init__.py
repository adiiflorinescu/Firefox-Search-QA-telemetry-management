# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/__init__.py

import os
from flask import Flask, g, session

def create_app(test_config=None):
    """Create and configure an instance of the Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',  # Change this for production
        DATABASE=os.path.join(app.instance_path, 'app.sqlite'),
        TC_BASE_URL="http://testrail.example.com/index.php?/cases/view/C"
    )

    if test_config is None:
        # Load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # Load the test config if passed in
        app.config.update(test_config)

    # Ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Move imports inside the factory function to avoid circular dependencies.
    from . import db
    from .db_migrations import run_migrations
    from .routes import auth, main, planning, user_management, management
    from . import commands
    from .services import database as db_service

    # Initialize the database and run migrations within the app context
    with app.app_context():
        db.init_app(app)
        run_migrations()

    # Register blueprints and commands
    commands.register_commands(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(planning.bp)
    app.register_blueprint(user_management.bp)
    app.register_blueprint(management.bp)

    # Make sure the main blueprint's 'metrics' view is available at the root
    app.add_url_rule('/', endpoint='main.metrics')

    # DEFINITIVE FIX: Update the filter to use index access instead of .get()
    def sort_details_filter(details):
        """
        Sorts coverage details by engine, then region, then TC ID.
        This works for both dicts and sqlite3.Row objects.
        """
        return sorted(
            details,
            key=lambda d: (
                d['engine'] or '',
                d['region'] or '',
                d['tc_id'] or ''
            )
        )

    # Register the filters with the Jinja environment
    app.jinja_env.filters['sort_details'] = sort_details_filter
    app.jinja_env.filters['strip_tcid_prefix'] = db_service._strip_tcid_prefix


    @app.before_request
    def load_logged_in_user():
        """If a user id is in the session, load the user object from the database into g.user."""
        user_id = session.get('user_id')
        if user_id is None:
            g.user = None
        else:
            # Use the correct service module to get the user
            g.user = db_service.get_user_by_id(user_id)

    return app