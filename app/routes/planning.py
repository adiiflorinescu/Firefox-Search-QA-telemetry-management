# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/routes/planning.py

from flask import Blueprint, render_template, request, jsonify, current_app, g
from ..services import database as db
from ..utils.decorators import login_required

bp = Blueprint('planning', __name__, url_prefix='/planning')


@bp.route('/')
@login_required
def view_planning():
    """Renders the new Coverage Planning page."""
    page_data = db.get_planning_page_data()
    return render_template(
        'planning.html',
        **page_data,
        tc_base_url=current_app.config.get('TC_BASE_URL', '')
    )


@bp.route('/update', methods=['POST'])
@login_required
def update_planning_entry():
    """Adds/updates/deletes a planning entry via AJAX."""
    data = request.get_json()
    try:
        result = db.update_planning_entry(data, g.user['user_id'])
        return jsonify(result)
    except Exception as e:
        current_app.logger.error(f"Error updating planning entry: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
