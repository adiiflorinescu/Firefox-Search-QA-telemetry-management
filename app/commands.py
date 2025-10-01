# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/commands.py

import click
from .db_migrations import run_migrations # Import the new migration runner

# The old init_db function is no longer needed, as run_migrations handles it.

@click.command('init-db')
def init_db_command():
    """
    Initializes or migrates the database to the latest version.
    This is safe to run multiple times.
    """
    try:
        run_migrations()
        click.echo('Database is up to date.')
    except Exception as e:
        click.echo(f'An error occurred during migration: {e}', err=True)


def register_commands(app):
    """Register all CLI commands with the Flask app."""
    app.cli.add_command(init_db_command)