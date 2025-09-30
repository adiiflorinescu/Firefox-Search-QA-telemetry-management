# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/utils/decorators.py

import functools
from flask import g, flash

def login_required(view):
    """View decorator that redirects anonymous users to the login page."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        from flask import redirect, url_for  # Local import
        if g.user is None:
            return redirect(url_for('auth.login'))
        return view(**kwargs)
    return wrapped_view


def admin_required(view):
    """
    View decorator that ensures the user is logged in and is an admin.
    This decorator implicitly includes login_required.
    """
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        from flask import redirect, url_for  # Local import
        # First, ensure the user is logged in.
        if g.user is None:
            return redirect(url_for('auth.login'))

        # Use index access for correctness with sqlite3.Row objects
        if g.user['role'] != 'admin':
            flash('You do not have permission to access this page.', 'error')
            # Redirect non-admins to a safe, default page.
            return redirect(url_for('main.metrics'))

        return view(**kwargs)
    return wrapped_view