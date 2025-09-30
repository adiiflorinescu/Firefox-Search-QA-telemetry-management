# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/routes/auth.py

from flask import Blueprint, render_template, request, redirect, url_for, session, g, flash
from werkzeug.security import check_password_hash
from ..db import get_db

bp = Blueprint('auth', __name__, url_prefix='/auth')

@bp.route('/login', methods=('GET', 'POST'))
def login():
    if g.user:
        return redirect(url_for('main.metrics'))

    if request.method == 'POST':
        # --- DEFINITIVE FIX: Use 'username' instead of 'email' ---
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        # --- DEFINITIVE FIX: Query by username ---
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

        if user is None:
            # --- DEFINITIVE FIX: Update flash message ---
            flash('Incorrect username.', 'error')
        elif not check_password_hash(user['password_hash'], password):
            flash('Incorrect password.', 'error')
        else:
            session.clear()
            session['user_id'] = user['user_id']
            return redirect(url_for('main.metrics'))

    return render_template('auth/login.html')

@bp.before_app_request
def load_logged_in_user():
    """If a user id is in the session, load the user object from the database into g.user."""
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        g.user = get_db().execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()

@bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('auth.login'))