# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/__init__.py

import os
from flask import Flask
from dotenv import load_dotenv


def create_app():
    """Create and configure an instance of the Flask application."""

    # --- DEFINITIVE FIX ---
    # Tell Flask where to find the templates folder.
    # The path is constructed relative to this __init__.py file:
    # '..' goes up from 'app/' to 'pythonProject/'
    # 'templates' goes into the correct folder.
    app = Flask(__name__,
                instance_relative_config=True,
                template_folder='../templates')

    # --- Load Configuration ---
    dotenv_path = os.path.join(app.instance_path, '..', '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)

    app.config.from_object('config')

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-default-secret-key-for-dev-only')
    app.config['DATABASE'] = os.path.join(app.instance_path, 'metrics.db')

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # --- Register Blueprints (Routes) ---
    from .routes import main, planning, management
    app.register_blueprint(main.bp)
    app.register_blueprint(planning.bp)
    app.register_blueprint(management.bp)

    # --- Register Custom Template Filters ---
    from .utils.template_filters import strip_tcid_prefix, sort_details
    app.jinja_env.filters['strip_tcid_prefix'] = strip_tcid_prefix
    app.jinja_env.filters['sort_details'] = sort_details

    return app