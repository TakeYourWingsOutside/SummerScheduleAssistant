# File: app/routes/schedule_api_routes.py

from flask import Blueprint, jsonify, request
from app import db
from app.models import Kid, Activity, ScheduledEvent
from datetime import datetime, timedelta, time
from app.services.schedule_utils import get_camp_session_start_date

# Use the same KID_COLORS dictionary or import it if it's moved to a central place
KID_COLORS = {
    "Reece": "#28a745",
    "Silas": "#007bff",
    "Sofia": "#ffc107",
    "Default": "#6c757d"
}

# Note the new blueprint name and URL prefix
bp_api = Blueprint('schedule_api', __name__, url_prefix='/schedule/api')

@bp_api.route('/events') # Will be accessible at /schedule/api/events
def api_get_events():
    start_str = request.args.get('start'); end_str = request.args.get('end'); kid_id_filter_str = request.args.get('kid_id')
    try:
        start_date_view = datetime.strptime(start_str.split('T')[0], '%Y-%m-%d').date()
        end_date_view_exclusive = datetime.strptime(end_str.split('T')[0], '%Y-%m-%d').date()
    except (ValueError, AttributeError, TypeError): # Added TypeError for None.split
        print(f"DEBUG API: Invalid start/end params for api_get_events: start='{start_str}', end='{end_str}'")
        return jsonify({"error": "Invalid date format from FullCalendar parameters"}), 400

    print(f"DEBUG API: api_get_events for range: {start_date_view} to {end_date_view_exclusive}, kid_filter: {kid_id_filter_str}")
    events_query = ScheduledEvent.query.filter(ScheduledEvent.date >= start_date_view, ScheduledEvent.date < end_date_view_exclusive)

    if kid_id_filter_str and kid_id_filter_str.lower() != 'all' and kid_id_filter_str != "":
        try: events_query = events_query.filter(ScheduledEvent.kid_id == int(kid_id_filter_str))
        except ValueError: pass # Ignore invalid filter

    scheduled_items_db = events_query.order_by(ScheduledEvent.start_time).all()
    calendar_events_fc = []
    for item_db in scheduled_items_db:
        kid_name = item_db.kid.name; kid_color = KID_COLORS.get(kid_name, KID_COLORS["Default"])
        title = item_db.activity_details.name; fc_all_day = False
        fc_start_dt = datetime.combine(item_db.date, item_db.start_time)
        fc_end_dt = datetime.combine(item_db.date, item_db.end_time)

        event_display_props = {}
        if item_db.is_camp:
            title += " (Camp)"
            event_display_props['borderColor'] = 'darkred'
            event_display_props['backgroundColor'] = '#fadadd'
            event_display_props['textColor'] = '#58181F'
            if item_db.is_overnight_camp:
                session_true_start_date = get_camp_session_start_date(item_db)
                session_true_end_date = item_db.camp_session_end_date
                if session_true_start_date and session_true_end_date and \
                        item_db.date > session_true_start_date and item_db.date < session_true_end_date:
                    fc_all_day = True
                    fc_start_dt = datetime.combine(item_db.date, time(0,0,0))
                    fc_end_dt = datetime.combine(item_db.date + timedelta(days=1), time(0,0,0))
                    event_display_props['backgroundColor'] = '#fce5d4'
                    event_display_props['borderColor'] = '#e67e22'
                    event_display_props['textColor'] = '#794B21'
        else:
            event_display_props['borderColor'] = kid_color
            event_display_props['backgroundColor'] = kid_color
            try:
                r, g, b = int(kid_color[1:3],16), int(kid_color[3:5],16), int(kid_color[5:7],16)
                event_display_props['textColor'] = '#fff' if (0.299*r + 0.587*g + 0.114*b)/255 < 0.5 else '#000'
            except: event_display_props['textColor'] = '#fff'

        calendar_events_fc.append({'id': item_db.id, 'title': title,
                                   'start': fc_start_dt.isoformat(), 'end': fc_end_dt.isoformat(), 'allDay': fc_all_day,
                                   'extendedProps': { 'kidName': kid_name, 'kidId': item_db.kid_id, 'status': item_db.status,
                                                      'description': item_db.activity_details.description, 'supervisor': item_db.supervisor_assigned,
                                                      'transport': item_db.transport_provider, 'kidColor': kid_color, 'isCamp': item_db.is_camp,
                                                      'isOvernightCamp': item_db.is_overnight_camp,
                                                      'cost': item_db.cost if item_db.cost and item_db.cost > 0 else None,
                                                      'campSessionId': item_db.camp_session_identifier }, **event_display_props })
    return jsonify(calendar_events_fc)

@bp_api.route('/kid_activities', methods=['GET']) # Will be /schedule/api/kid_activities
def api_get_activities_for_kid():
    kid_id_str = request.args.get('kid_id')
    if not kid_id_str: return jsonify({"error": "Missing kid_id"}), 400
    try: kid_id = int(kid_id_str)
    except ValueError: return jsonify({"error": "Invalid kid_id"}), 400
    kid = Kid.query.get(kid_id)
    if not kid: return jsonify({"error": "Kid not found"}), 404
    activities_data = []
    try:
        kid_activities = kid.activities.filter_by(is_camp_activity=False).order_by(Activity.name).all()
        activities_data = [{"id": act.id, "name": act.name, "duration_minutes": act.duration_minutes} for act in kid_activities]
    except AttributeError:
        if isinstance(kid.activities, list):
            sorted_acts = sorted([a for a in kid.activities if not a.is_camp_activity], key=lambda x: x.name)
            activities_data = [{"id": act.id, "name": act.name, "duration_minutes": act.duration_minutes} for act in sorted_acts]
    return jsonify(activities_data)

@bp_api.route('/event/update_time', methods=['POST']) # Will be /schedule/api/event/update_time
def api_update_event_time():
    data = request.get_json()
    if not data: return jsonify({"success": False, "message": "Invalid request"}), 400
    try: event_id = int(data.get('id')); new_start_str = data.get('new_start'); new_end_str = data.get('new_end')
    except (TypeError, ValueError): return jsonify({"success": False, "message": "Invalid ID format"}), 400
    if not all([event_id, new_start_str, new_end_str]): return jsonify({"success": False, "message": "Missing data"}), 400
    event = ScheduledEvent.query.get(event_id)
    if not event: return jsonify({"success": False, "message": "Event not found"}), 404
    try: new_start_dt = datetime.strptime(new_start_str, '%Y-%m-%d %H:%M:%S'); new_end_dt = datetime.strptime(new_end_str, '%Y-%m-%d %H:%M:%S')
    except ValueError: return jsonify({"success": False, "message": "Invalid date format"}), 400
    new_date, new_start_time, new_end_time = new_start_dt.date(), new_start_dt.time(), new_end_dt.time()
    if event.is_camp and event.camp_session_identifier:
        session_start_date = get_camp_session_start_date(event); session_end_date = event.camp_session_end_date
        if new_date < session_start_date or new_date > session_end_date:
            return jsonify({"success": False, "message": "Camp day cannot move outside session range."}), 409
    conflict = ScheduledEvent.query.filter(ScheduledEvent.kid_id == event.kid_id, ScheduledEvent.date == new_date,
                                           ScheduledEvent.start_time < new_end_time, ScheduledEvent.end_time > new_start_time,
                                           ScheduledEvent.id != event.id).first()
    if conflict: return jsonify({"success": False, "message": f"Time conflict with '{conflict.activity_details.name}'."}), 409
    if event.linked_event_id:
        linked_event = ScheduledEvent.query.get(event.linked_event_id)
        if linked_event:
            linked_conflict = ScheduledEvent.query.filter(ScheduledEvent.kid_id == linked_event.kid_id, ScheduledEvent.date == new_date,
                                                          ScheduledEvent.start_time < new_end_time, ScheduledEvent.end_time > new_start_time,
                                                          ScheduledEvent.id != linked_event.id).first()
            if linked_conflict: return jsonify({"success": False, "message": f"Update conflicts for partner: '{linked_conflict.activity_details.name}'."}), 409
            linked_event.date, linked_event.start_time, linked_event.end_time = new_date, new_start_time, new_end_time
    event.date, event.start_time, event.end_time = new_date, new_start_time, new_end_time
    try: db.session.commit(); return jsonify({"success": True, "message": "Event updated."})
    except Exception as e: db.session.rollback(); print(f"API Update Error: {e}"); return jsonify({"success": False, "message": str(e)}), 500

@bp_api.route('/event/create', methods=['POST']) # Will be /schedule/api/event/create
def api_create_event():
    data = request.get_json()
    if not data: return jsonify({"success": False, "message": "No data"}), 400
    try: kid_id = int(data.get('kid_id')); activity_id = int(data.get('activity_id'))
    except (TypeError, ValueError): return jsonify({"success": False, "message": "Invalid ID format"}), 400
    start_datetime_str = data.get('start_datetime'); notes = data.get('notes', '')
    if not all([kid_id, activity_id, start_datetime_str]): return jsonify({"success": False, "message": "Missing fields"}), 400
    kid = Kid.query.get(kid_id); activity = Activity.query.get(activity_id)
    if not kid or not activity: return jsonify({"success": False, "message": "Kid/Activity not found"}), 404
    if activity.is_camp_activity: return jsonify({"success": False, "message": "Cannot quick-add Camp Definitions. Use 'Schedule Camp Session'."}), 400
    try:
        start_dt = datetime.strptime(start_datetime_str, '%Y-%m-%d %H:%M:%S')
        event_date, event_start_time = start_dt.date(), start_dt.time()
        end_dt = start_dt + timedelta(minutes=activity.duration_minutes); event_end_time = end_dt.time()
    except ValueError: return jsonify({"success": False, "message": "Invalid date format"}), 400
    conflict = ScheduledEvent.query.filter(ScheduledEvent.kid_id == kid_id, ScheduledEvent.date == event_date,
                                           ScheduledEvent.start_time < event_end_time, ScheduledEvent.end_time > event_start_time).first()
    if conflict: return jsonify({"success": False, "message": f"Time conflict: '{conflict.activity_details.name}'."}), 409
    status = "Needs Partner (Modal Add)" if activity.requires_another_person and not activity.can_do_alone else "Scheduled"
    new_event = ScheduledEvent(kid_id=kid_id, activity_id=activity_id, date=event_date, start_time=event_start_time,
                               end_time=event_end_time, notes=notes, status=status, is_camp=False, cost=None, is_overnight_camp=False,
                               camp_session_identifier=None, camp_session_end_date=None )
    db.session.add(new_event)
    try: db.session.commit(); return jsonify({"success": True, "message": "Event created.", "event_id": new_event.id})
    except Exception as e: db.session.rollback(); print(f"API Create Error: {e}"); return jsonify({"success": False, "message": str(e)}), 500
