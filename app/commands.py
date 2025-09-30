# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/commands.py

import click
import os
from .db import get_db


def init_db():
    """Clear existing data and create new tables."""
    # Import current_app here, only when the function is actually called.
    from flask import current_app

    db = get_db()
    # Use current_app.root_path to reliably find the schema.sql file
    schema_path = os.path.join(current_app.root_path, '..', 'schema.sql')
    with open(schema_path, 'r', encoding='utf-8') as f:
        db.executescript(f.read())


@click.command('init-db')
def init_db_command():
    """Clear existing data and create new tables."""
    init_db()
    click.echo('Initialized the database.')


def register_commands(app):
    """Register all CLI commands with the Flask app."""
    app.cli.add_command(init_db_command)