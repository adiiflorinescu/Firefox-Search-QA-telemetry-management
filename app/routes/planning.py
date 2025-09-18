# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/routes/planning.py

from flask import Blueprint, render_template, request, jsonify, session, current_app
from ..services import database as db
# from .. import config <- REMOVE THIS LINE

bp = Blueprint('planning', __name__, url_prefix='/planning')


@bp.route('/')
def view_planning():
    """Renders the new Coverage Planning page."""
    planning_data, existing_tcs, planned_tcs = db.get_planning_page_data()

    return render_template(
        'planning.html',
        planning_data=planning_data,
        metric_to_existing_tcs=existing_tcs,
        metric_to_planned_tcs=planned_tcs,
        # Use current_app.config to access configuration
        tc_base_url=current_app.config['TC_BASE_URL'],
        show_management=session.get('show_management', False)
    )


@bp.route('/update', methods=['POST'])
def update_planning_entry():
    """Adds/updates/deletes a planning entry via AJAX."""
    data = request.get_json()
    try:
        result = db.update_planning_entry(data)
        return jsonify(result)
    except Exception as e:
        # Log the exception e
        current_app.logger.error(f"Error updating planning entry: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500