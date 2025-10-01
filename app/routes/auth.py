# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/routes/auth.py

from flask import Blueprint, render_template, request, redirect, url_for, session, g, flash
from werkzeug.security import check_password_hash
from ..services import database as db

bp = Blueprint('auth', __name__, url_prefix='/auth')


@bp.route('/login', methods=('GET', 'POST'))
def login():
    if g.user:
        return redirect(url_for('main.metrics'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # We use the function from our services layer now
        user = db.get_db().execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

        if user is None:
            flash('Incorrect username.', 'error')
        elif not check_password_hash(user['password_hash'], password):
            flash('Incorrect password.', 'error')
        else:
            session.clear()
            session['user_id'] = user['user_id']
            return redirect(url_for('main.metrics'))

    return render_template('auth/login.html')


# The @bp.before_app_request function has been removed from this file
# and its logic was moved into the application factory in __init__.py.

@bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('auth.login'))