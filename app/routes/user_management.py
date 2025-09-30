# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/routes/user_management.py

from flask import Blueprint, render_template, request, flash, redirect, url_for, g
from werkzeug.security import generate_password_hash
from ..services import database as db

bp = Blueprint('user_management', __name__, url_prefix='/users')


def require_admin_privileges():
    """Checks for admin role before processing any request for this blueprint."""
    if g.user is None:
        return redirect(url_for('auth.login'))

    if g.user['role'] != 'admin':
        flash('You do not have permission to access this page.', 'error')
        return redirect(url_for('main.metrics'))


bp.before_request(require_admin_privileges)


@bp.route('/')
def index():
    """Renders the main user management page."""
    users = db.get_all_users()
    return render_template('user_management/index.html', users=users)


@bp.route('/add', methods=('GET', 'POST'))
def add_user():
    """Handles adding a new user."""
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']

        if not all([username, email, password, role]):
            flash('All fields are required.', 'error')
        else:
            password_hash = generate_password_hash(password)
            success, message = db.add_user(username, email, password_hash, role, g.user['user_id'])
            flash(message, 'success' if success else 'error')
            if success:
                return redirect(url_for('user_management.index'))

    return render_template('user_management/add.html')


@bp.route('/delete/<int:user_id>', methods=('POST',))
def delete_user(user_id):
    """Handles deleting a user."""
    if user_id == g.user['user_id']:
        flash('You cannot delete your own account.', 'error')
    else:
        success, message = db.delete_user(user_id, g.user['user_id'])
        flash(message, 'success' if success else 'error')
    return redirect(url_for('user_management.index'))


@bp.route('/edit/<int:user_id>', methods=('GET', 'POST'))
def edit_user(user_id):
    """Handles editing an existing user's profile."""
    user = db.get_user_by_id(user_id)
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('user_management.index'))

    if request.method == 'POST':
        # Prevent an admin from accidentally demoting themselves
        if user_id == g.user['user_id'] and request.form['role'] != 'admin':
            flash('You cannot remove your own admin privileges.', 'error')
            return render_template('user_management/edit.html', user=user)

        success, message = db.update_user(user_id, request.form, g.user['user_id'])
        flash(message, 'success' if success else 'error')
        if success:
            return redirect(url_for('user_management.index'))

    return render_template('user_management/edit.html', user=user)