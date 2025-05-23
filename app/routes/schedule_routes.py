from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from app import db
from app.models import Kid, Activity, ScheduledEvent
from app.forms import (
    SelectDateKidForm, ScheduleActivityForm, ScheduleRangeForm,
    EditScheduledEventDetailsForm, ScheduleCampSessionForm,
    BatchScheduleMultiDateForm, ExportForm, EditCampSessionForm # Ensure all form imports are correct
)
from datetime import datetime, timedelta, date, time
from app.services.scheduling_service import auto_schedule_day, TARGET_DAILY_MINUTES
from app.services.schedule_utils import get_camp_session_start_date
import uuid

bp = Blueprint('schedule', __name__, url_prefix='/schedule')

# --- Daily View and Manual Add/Delete (Regular Activities) ---
@bp.route('/', methods=['GET', 'POST'])
def view_day_schedule():
    selection_form = SelectDateKidForm()
    schedule_form = ScheduleActivityForm()
    selected_kid = None
    selected_date_obj = selection_form.date.data
    scheduled_events = []

    if request.method == 'POST' and selection_form.submit_select.data and selection_form.validate_on_submit():
        selected_date_obj = selection_form.date.data
        kid_id = selection_form.kid_id.data
        if kid_id and kid_id != 0:
            selected_kid = Kid.query.get(kid_id)
            if selected_kid:
                schedule_form = ScheduleActivityForm(kid_id=selected_kid.id)
                scheduled_events = ScheduledEvent.query.filter_by(kid_id=selected_kid.id, date=selected_date_obj) \
                    .join(Activity).order_by(ScheduledEvent.start_time, Activity.name).all()
        else:
            flash("Please select a kid.", "error"); schedule_form = ScheduleActivityForm()
    elif request.method == 'GET':
        query_date_str = request.args.get('date'); query_kid_id_str = request.args.get('kid_id')
        if query_date_str and query_kid_id_str:
            try:
                selected_date_obj = datetime.strptime(query_date_str, '%Y-%m-%d').date(); kid_id_int = int(query_kid_id_str)
                selected_kid = Kid.query.get(kid_id_int)
                if selected_kid:
                    selection_form.date.data = selected_date_obj; selection_form.kid_id.data = kid_id_int
                    schedule_form = ScheduleActivityForm(kid_id=selected_kid.id)
                    scheduled_events = ScheduledEvent.query.filter_by(kid_id=selected_kid.id, date=selected_date_obj) \
                        .join(Activity).order_by(ScheduledEvent.start_time, Activity.name).all()
                else: flash("Kid not found.", "error"); selected_kid=None; selected_date_obj=None
            except ValueError: flash("Invalid URL params.", "error"); selected_kid=None; selected_date_obj=None

    return render_template('schedule/view_day.html', selection_form=selection_form, schedule_form=schedule_form,
                           selected_kid=selected_kid, selected_date=selected_date_obj,
                           scheduled_events=scheduled_events, TARGET_DAILY_MINUTES=TARGET_DAILY_MINUTES)

@bp.route('/add_event/<int:kid_id>/<schedule_date_str>', methods=['POST'])
def add_event_to_day(kid_id, schedule_date_str): # ONLY for REGULAR activities
    initiating_kid = Kid.query.get_or_404(kid_id)
    try: event_date = datetime.strptime(schedule_date_str, '%Y-%m-%d').date()
    except ValueError: flash("Invalid date format.", "error"); return redirect(url_for('schedule.view_day_schedule'))

    form = ScheduleActivityForm(kid_id=initiating_kid.id)
    if form.validate_on_submit():
        activity = Activity.query.get(form.activity_id.data)
        if not activity or form.activity_id.data == 0 or activity.is_camp_activity: # Check it's not a camp def
            flash("Please select a valid regular (non-camp) activity.", "error")
            s_form = SelectDateKidForm(date=event_date, kid_id=kid_id); s_events = ScheduledEvent.query.filter_by(kid_id=kid_id, date=event_date).all()
            return render_template('schedule/view_day.html', selection_form=s_form, schedule_form=form,
                                   selected_kid=initiating_kid, selected_date=event_date, scheduled_events=s_events, TARGET_DAILY_MINUTES=TARGET_DAILY_MINUTES)

        start_time = form.start_time.data; start_dt = datetime.combine(event_date, start_time)
        end_time = (start_dt + timedelta(minutes=activity.duration_minutes)).time()

        partner_kid_event = None # Full partner logic should be re-inserted here if needed
        if activity.requires_another_person and not activity.can_do_alone:
            # Simplified: just flash warning, actual partner finding was more complex
            flash(f"Warning: '{activity.name}' typically requires a partner. This was scheduled for {initiating_kid.name} only.", "warning")

        initiating_kid_conflict = ScheduledEvent.query.filter(
            ScheduledEvent.kid_id == initiating_kid.id, ScheduledEvent.date == event_date,
            ScheduledEvent.start_time < end_time, ScheduledEvent.end_time > start_time
        ).first()

        if initiating_kid_conflict:
            flash(f"Time conflict for {initiating_kid.name} with '{initiating_kid_conflict.activity_details.name}'.", 'error')
        else:
            initiating_kid_event_status = "Confirmed (Partner Pending)" if partner_kid_event else "Scheduled"
            new_event = ScheduledEvent(
                kid_id=initiating_kid.id, activity_id=activity.id, date=event_date,
                start_time=start_time, end_time=end_time, status=initiating_kid_event_status,
                supervisor_assigned=form.supervisor_assigned.data, transport_provider=form.transport_provider.data,
                notes=form.notes.data, is_camp=False,
                cost=None, is_overnight_camp=False, camp_session_identifier=None, camp_session_end_date=None
            )
            db.session.add(new_event)
            if partner_kid_event: db.session.add(partner_kid_event) # Add partner if one was created
            try:
                db.session.commit()
                if new_event.id and partner_kid_event and partner_kid_event.id: # Link if both created
                    new_event.linked_event_id = partner_kid_event.id
                    partner_kid_event.linked_event_id = new_event.id
                    db.session.commit()
                flash(f"'{activity.name}' added to {initiating_kid.name}'s schedule.", 'success')
            except Exception as e: db.session.rollback(); flash(f"Error adding event(s): {str(e)}", "error")
    else:
        s_form = SelectDateKidForm(date=event_date, kid_id=kid_id); s_events = ScheduledEvent.query.filter_by(kid_id=kid_id, date=event_date).all()
        for f, errs in form.errors.items(): [flash(f"Error in {getattr(form,f).label.text if hasattr(getattr(form,f),'label') else f}: {e}", "danger") for e in errs] # Corrected flash for form errors
        return render_template('schedule/view_day.html', selection_form=s_form, schedule_form=form,
                               selected_kid=initiating_kid, selected_date=event_date, scheduled_events=s_events, TARGET_DAILY_MINUTES=TARGET_DAILY_MINUTES)
    return redirect(url_for('schedule.view_day_schedule', date=schedule_date_str, kid_id=kid_id))

# --- Quick Schedule Single Regular Activity (from Activities Page) ---
@bp.route('/activity/schedule/<int:activity_id>', methods=['GET', 'POST'])
def schedule_single_activity_form(activity_id):
    activity = Activity.query.filter_by(id=activity_id, is_camp_activity=False).first_or_404()
    form = QuickScheduleRegularActivityForm(activity_obj=activity)
    if form.validate_on_submit():
        kid_id = form.kid_id.data; schedule_date = form.schedule_date.data; start_time = form.start_time.data
        kid = Kid.query.get(kid_id)
        if not kid or kid_id == 0 : flash("Invalid kid selected.", "error")
        else:
            start_datetime = datetime.combine(schedule_date, start_time)
            end_time = (start_datetime + timedelta(minutes=activity.duration_minutes)).time()
            status = "Scheduled (Quick Add)"
            if activity.requires_another_person and not activity.can_do_alone: status = "Needs Partner (Quick Add)"; flash(f"'{activity.name}' may need a partner.", "warning")
            conflict = ScheduledEvent.query.filter(ScheduledEvent.kid_id == kid.id, ScheduledEvent.date == schedule_date, ScheduledEvent.start_time < end_time, ScheduledEvent.end_time > start_time).first()
            if conflict: flash(f"Time conflict for {kid.name} with '{conflict.activity_details.name}'.", 'error')
            else:
                new_event = ScheduledEvent(kid_id=kid.id, activity_id=activity.id, date=schedule_date, start_time=start_time,
                                           end_time=end_time, status=status, supervisor_assigned=form.supervisor_assigned.data,
                                           transport_provider=form.transport_provider.data, notes=form.notes.data, is_camp=False)
                db.session.add(new_event)
                try: db.session.commit(); flash(f"'{activity.name}' scheduled for {kid.name}.", 'success'); return redirect(url_for('schedule.view_day_schedule', date=schedule_date.strftime('%Y-%m-%d'), kid_id=kid.id))
                except Exception as e: db.session.rollback(); flash(f"Error: {str(e)}", "error")
    elif request.method == 'POST' and form.errors:
        for f, errs in form.errors.items(): [flash(f"Error in {getattr(form,f).label.text if hasattr(getattr(form,f),'label') else f}: {e}", "danger") for e in errs]
    return render_template('schedule/schedule_single_activity.html', form=form, activity=activity)

# --- Batch Schedule Regular Activity (Multiple Dates, Single Time) ---
@bp.route('/batch_schedule_multi_date', methods=['GET', 'POST'])
def batch_schedule_activity_multi_date():
    form = BatchScheduleMultiDateForm()
    if form.validate_on_submit():
        activity_id = form.activity_id.data; kid_id = form.kid_id.data
        selected_dates_str = form.selected_dates.data; start_time = form.start_time.data
        activity = Activity.query.get(activity_id); kid = Kid.query.get(kid_id)
        if not activity or activity.is_camp_activity: flash("Select a valid regular activity.", "error")
        elif not kid or kid_id == 0: flash("Select a valid kid.", "error")
        elif not selected_dates_str: flash("Select at least one date.", "error")
        else:
            dates_to_schedule = []
            for date_str in selected_dates_str.split(','):
                if date_str.strip():
                    try: dates_to_schedule.append(datetime.strptime(date_str.strip(), '%Y-%m-%d').date())
                    except ValueError: flash(f"Invalid date format: {date_str}. Skipped.", "warning")
            if not dates_to_schedule: flash("No valid dates processed.", "warning")
            else:
                success_count = 0; failure_count = 0; events_to_add = []
                for schedule_date in dates_to_schedule:
                    end_time = (datetime.combine(schedule_date, start_time) + timedelta(minutes=activity.duration_minutes)).time()
                    conflict = ScheduledEvent.query.filter(ScheduledEvent.kid_id == kid.id, ScheduledEvent.date == schedule_date, ScheduledEvent.start_time < end_time, ScheduledEvent.end_time > start_time).first()
                    if conflict: flash(f"Conflict on {schedule_date.strftime('%b %d')} with '{conflict.activity_details.name}'. Skipped.", 'warning'); failure_count += 1; continue
                    status = "Needs Partner (Batch)" if activity.requires_another_person and not activity.can_do_alone else "Scheduled (Batch)"
                    events_to_add.append(ScheduledEvent(kid_id=kid.id, activity_id=activity.id, date=schedule_date, start_time=start_time, end_time=end_time,
                                                        status=status, supervisor_assigned=form.supervisor_assigned.data or None, transport_provider=form.transport_provider.data or None,
                                                        notes=form.notes.data or None, is_camp=False))
                    success_count += 1
                if events_to_add: db.session.add_all(events_to_add)
                if success_count > 0 or failure_count > 0:
                    try:
                        db.session.commit()
                        if success_count > 0: flash(f"Batch: {success_count} event(s) for '{activity.name}' scheduled.", 'success')
                        if failure_count > 0: flash(f"{failure_count} event(s) skipped.", 'warning')
                    except Exception as e: db.session.rollback(); flash(f"Error: {str(e)}", "error")
            return redirect(url_for('schedule.batch_schedule_activity_multi_date'))
    elif request.method == 'POST' and form.errors:
        for f, errs in form.errors.items(): [flash(f"Error in {getattr(form,f).label.text if hasattr(getattr(form,f),'label') else f}: {e}", "danger") for e in errs]
    return render_template('schedule/batch_schedule_activity.html', form=form)

# --- Camp Session Scheduling ---
@bp.route('/camp_session/new/<int:activity_id>', methods=['GET', 'POST'])
def schedule_camp_session_form(activity_id):
    camp_activity_definition = Activity.query.filter_by(id=activity_id, is_camp_activity=True).first_or_404()
    form_kwargs = {};
    if request.method == 'GET':
        form_kwargs.update({ 'activity_obj': camp_activity_definition, 'session_start_date': date.today(),
                             'session_end_date': date.today() + timedelta(days=4),
                             'session_is_overnight': camp_activity_definition.default_is_overnight,
                             'session_cost': camp_activity_definition.default_camp_cost })
    form = ScheduleCampSessionForm(**form_kwargs)
    if form.validate_on_submit():
        kid_id=form.kid_id.data; s_s_date=form.session_start_date.data; s_e_date=form.session_end_date.data
        s_cost=form.session_cost.data if form.session_cost.data is not None else camp_activity_definition.default_camp_cost or 0.0
        s_is_overnight=form.session_is_overnight.data; s_notes=form.notes.data
        kid = Kid.query.get(kid_id)
        if not kid or kid_id == 0: flash("Kid not found.", "error"); return render_template('schedule/schedule_camp_session.html', form=form, activity=camp_activity_definition)
        sess_id = str(uuid.uuid4()); c_date = s_s_date; days_c = 0; ev_add = []
        while c_date <= s_e_date:
            daily_s_time_def = time(9,0)
            daily_e_time = (datetime.combine(c_date, daily_s_time_def) + timedelta(minutes=camp_activity_definition.duration_minutes)).time()
            if s_is_overnight:
                if c_date == s_s_date: daily_e_time = time(23,59,59)
                elif c_date == s_e_date: daily_s_time_def = time(0,0,0)
                else: daily_s_time_def, daily_e_time = time(0,0,0), time(23,59,59)
            conflict = ScheduledEvent.query.filter(ScheduledEvent.kid_id == kid.id, ScheduledEvent.date == c_date, ScheduledEvent.start_time < daily_e_time, ScheduledEvent.end_time > daily_s_time_def).first()
            if conflict: flash(f"Conflict on {c_date.strftime('%Y-%m-%d')} with '{conflict.activity_details.name}'. Aborted.", 'error'); return render_template('schedule/schedule_camp_session.html', form=form, activity=camp_activity_definition)
            camp_ev = ScheduledEvent(kid_id=kid.id, activity_id=camp_activity_definition.id, date=c_date, start_time=daily_s_time_def, end_time=daily_e_time,
                                     status="Scheduled (Camp)", notes=s_notes, is_camp=True, cost=s_cost if days_c == 0 else 0.0,
                                     is_overnight_camp=s_is_overnight, camp_session_identifier=sess_id, camp_session_end_date=s_e_date)
            ev_add.append(camp_ev); days_c +=1; c_date += timedelta(days=1)
        if ev_add:
            db.session.add_all(ev_add)
            try: db.session.commit(); flash(f"Camp '{camp_activity_definition.name}' scheduled for {kid.name}.", 'success'); return redirect(url_for('schedule.view_day_schedule', date=s_s_date.strftime('%Y-%m-%d'), kid_id=kid.id))
            except Exception as e: db.session.rollback(); flash(f"Error: {str(e)}", "error")
        else: flash("No camp days generated.", "info")
    elif request.method == 'POST' and form.errors:
        for f, errs in form.errors.items(): [flash(f"Error in {getattr(form,f).label.text if hasattr(getattr(form,f),'label') else f}: {e}", "danger") for e in errs]
    return render_template('schedule/schedule_camp_session.html', form=form, activity=camp_activity_definition)

# --- General Event Management & Auto-Scheduling ---
@bp.route('/delete_event/<int:event_id>', methods=['POST'])
def delete_scheduled_event(event_id):
    event = ScheduledEvent.query.get(event_id) # Use get() instead of get_or_404 for API
    if not event:
        return jsonify({"success": False, "message": "Event not found."}), 404

    activity_name = event.activity_details.name if event.activity_details else "Unknown Event"
    is_first_day_of_camp_with_cost = False
    cost_transfer_message = None

    # --- Cost transfer logic for camps (if applicable) ---
    if event.is_camp and event.cost and event.cost > 0 and event.camp_session_identifier:
        is_first_day_of_camp_with_cost = True # Assume it is, or was

        next_day_event = ScheduledEvent.query.filter(
            ScheduledEvent.camp_session_identifier == event.camp_session_identifier,
            ScheduledEvent.kid_id == event.kid_id,
            ScheduledEvent.date > event.date
        ).order_by(ScheduledEvent.date.asc()).first()

        if next_day_event:
            next_day_event.cost = event.cost
            cost_transfer_message = f"Cost of '{activity_name}' session transferred to {next_day_event.date.strftime('%Y-%m-%d')}."
            # db.session.add(next_day_event) # Not strictly needed if already in session
        # else: No next day to transfer cost to.
    # --- End cost transfer logic ---

    try:
        db.session.delete(event)
        db.session.commit()

        final_message = f"Event '{activity_name}' removed successfully."
        if cost_transfer_message:
            final_message += f" {cost_transfer_message}"
        elif is_first_day_of_camp_with_cost: # Cost was on it, but no next day to transfer to
            final_message += " This was the primary cost entry for its camp session."

        return jsonify({"success": True, "message": final_message})
    except Exception as e:
        db.session.rollback()
        print(f"ERROR (delete_scheduled_event API): {str(e)}") # Log to server
        return jsonify({"success": False, "message": f"Error removing event: {str(e)}"}), 500

@bp.route('/event/<int:event_id>/edit_details', methods=['GET', 'POST'])
def edit_scheduled_event_details(event_id):
    event = ScheduledEvent.query.get_or_404(event_id); form = EditScheduledEventDetailsForm(obj=event)
    f_day_camp_date=None; dis_cost=False; cost_title=""
    if event.is_camp and event.camp_session_identifier:
        f_day_camp_date = get_camp_session_start_date(event)
        if event.date != f_day_camp_date: dis_cost=True; cost_title='Cost managed on first day.'
    if request.method == 'GET': # Apply render_kw for GET
        if event.is_camp:
            if not hasattr(form.is_camp, 'render_kw') or form.is_camp.render_kw is None: form.is_camp.render_kw = {}
            form.is_camp.render_kw['disabled']=True
        if dis_cost:
            if not hasattr(form.cost, 'render_kw') or form.cost.render_kw is None: form.cost.render_kw = {}
            form.cost.render_kw={'disabled':True, 'title':cost_title}
    if form.validate_on_submit() and form.submit_edit_details.data:
        event.supervisor_assigned=form.supervisor_assigned.data; event.transport_provider=form.transport_provider.data
        event.notes=form.notes.data;
        if form.status.data: event.status=form.status.data
        # Check render_kw before trying to access .get on it
        if not (hasattr(form.is_overnight_camp, 'render_kw') and form.is_overnight_camp.render_kw and form.is_overnight_camp.render_kw.get('disabled')):
            event.is_overnight_camp=form.is_overnight_camp.data
        if not dis_cost:
            if event.is_camp and f_day_camp_date and event.date == f_day_camp_date:
                first_ev = ScheduledEvent.query.filter_by(camp_session_identifier=event.camp_session_identifier, kid_id=event.kid_id, date=f_day_camp_date).first()
                if first_ev: first_ev.cost = form.cost.data
                if event.id == first_ev.id: event.cost = form.cost.data
            elif not event.is_camp: event.cost = form.cost.data
        try: db.session.commit(); flash("Details updated.", 'success'); return redirect(url_for('schedule.view_day_schedule',date=event.date.strftime('%Y-%m-%d'), kid_id=event.kid_id))
        except Exception as e: db.session.rollback(); flash(f"Error: {str(e)}", "error")
    if form.errors and request.method == 'POST': # Re-apply disabled state if form re-renders due to other errors
        if event.is_camp:
            if not hasattr(form.is_camp, 'render_kw') or form.is_camp.render_kw is None: form.is_camp.render_kw = {}
            form.is_camp.render_kw['disabled']=True
        if dis_cost:
            if not hasattr(form.cost, 'render_kw') or form.cost.render_kw is None: form.cost.render_kw = {}
            form.cost.render_kw={'disabled':True, 'title':cost_title}
        for f, errs in form.errors.items(): [flash(f"Error in {getattr(form,f).label.text if hasattr(getattr(form,f),'label') else f}: {e}", "danger") for e in errs]
    return render_template('schedule/edit_event_details.html', form=form, event=event)

@bp.route('/confirm_event/<int:event_id>/<decision>', methods=['POST'])
def confirm_event(event_id, decision):
    event = ScheduledEvent.query.get_or_404(event_id); r_kid_id=event.kid_id; r_date_str=event.date.strftime('%Y-%m-%d')
    if event.status != "Pending Confirmation": flash("Not pending.", "warning")
    elif decision == "confirmed":
        event.status = "Confirmed"
        if event.linked_event_id:
            l_event = ScheduledEvent.query.get(event.linked_event_id)
            if l_event and l_event.status == "Confirmed (Partner Pending)": l_event.status = "Confirmed"
        flash(f"Event confirmed.", "success")
    elif decision == "declined":
        name = event.activity_details.name
        if event.linked_event_id:
            l_event = ScheduledEvent.query.get(event.linked_event_id)
            if l_event: db.session.delete(l_event)
        db.session.delete(event); flash(f"Event '{name}' declined & removed.", "info")
    else: flash("Invalid decision.", "error"); return redirect(url_for('schedule.view_day_schedule', date=r_date_str, kid_id=r_kid_id))
    try: db.session.commit()
    except Exception as e: db.session.rollback(); flash(f"Error: {str(e)}", "error")
    return redirect(url_for('schedule.view_day_schedule', date=r_date_str, kid_id=r_kid_id))

@bp.route('/auto_schedule/<int:kid_id>/<schedule_date_str>', methods=['POST'])
def trigger_auto_schedule_day(kid_id, schedule_date_str):
    kid=Kid.query.get_or_404(kid_id);
    try: s_date=datetime.strptime(schedule_date_str, '%Y-%m-%d').date()
    except ValueError: flash("Invalid date.", "error"); return redirect(url_for('schedule.view_day_schedule'))
    succ, msg = auto_schedule_day(kid.id, s_date); flash(msg, 'success' if succ else 'error')
    return redirect(url_for('schedule.view_day_schedule', date=schedule_date_str, kid_id=kid_id))

@bp.route('/range', methods=['GET', 'POST'])
def trigger_range_schedule(): # For auto-scheduling regular activities
    form = ScheduleRangeForm()
    if form.validate_on_submit() and form.submit_range_schedule.data:
        kid_id=form.kid_id.data; s_date=form.start_date.data; e_date=form.end_date.data
        if kid_id == 0: flash("Select a kid.", "error")
        else:
            kid = Kid.query.get(kid_id); c_date = s_date; successes, errors = [], []; days_p = 0
            max_d = min((e_date - s_date).days + 1, 31 if (e_date - s_date).days + 1 > 0 else 1)
            while c_date <= e_date and days_p < max_d:
                days_p += 1; succ, msg = auto_schedule_day(kid.id, c_date)
                if succ and ("Auto-scheduled" in msg or "activities added" in msg): successes.append(f"{c_date.strftime('%Y-%m-%d')}: {msg}")
                elif not succ or "No suitable" in msg or "already sufficiently" in msg : errors.append(f"{c_date.strftime('%Y-%m-%d')}: {msg}") # Capture all non-explicit successes as errors/warnings
                c_date += timedelta(days=1)
            if successes: flash("Range scheduling - successful days:", 'info'); [flash(msg, 'success') for msg in successes]
            if errors: flash("Range scheduling - days with issues/no new events:", 'info'); [flash(msg, 'warning' if "already" in msg or "No suitable" in msg else 'error') for msg in errors]
            if not successes and not errors and days_p > 0: flash("No new activities were auto-scheduled for the selected range.", 'info')
            elif days_p == 0 : flash("No days processed in range.", "warning")
            return redirect(url_for('schedule.trigger_range_schedule'))
    elif request.method == 'POST' and form.errors:
        for f, errs in form.errors.items(): [flash(f"Error in {getattr(form,f).label.text if hasattr(getattr(form,f),'label') else f}: {e}", "danger") for e in errs]
    return render_template('schedule/schedule_range.html', form=form, TARGET_DAILY_MINUTES=TARGET_DAILY_MINUTES)

# --- Route for FullCalendar Page (this is user-facing, not API) ---
@bp.route('/week')
def view_week_schedule():
    all_kids = Kid.query.order_by(Kid.name).all()
    return render_template('schedule/view_week.html', all_kids_for_modal=all_kids)

# --- Route for Clearing All Scheduled Events ---
@bp.route('/clear_all_scheduled_events', methods=['POST'])
def clear_all_scheduled_events():
    activities_in_use = db.session.query(ScheduledEvent.id).limit(1).first() # More efficient check
    if activities_in_use: # Check if any scheduled events exist at all
        # Actually, the FK constraint on Activity means we can't delete activities if scheduled events exist.
        # But we CAN delete scheduled events regardless of activities.
        pass # No pre-check needed here for clearing ScheduledEvents themselves.

    try:
        num_deleted = db.session.query(ScheduledEvent).delete()
        db.session.commit()
        flash(f"Successfully cleared {num_deleted} scheduled event(s).", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Error clearing scheduled events: {str(e)}", 'error')
    return redirect(url_for('schedule.view_day_schedule'))

@bp.route('/camp_session/edit/<int:kid_id>/<camp_session_id>', methods=['GET', 'POST'])
def edit_camp_session(kid_id, camp_session_id):
    # Find the first event of this camp session to get master details like activity_id
    master_event = ScheduledEvent.query.filter_by(
        kid_id=kid_id,
        camp_session_identifier=camp_session_id,
        is_camp=True
    ).order_by(ScheduledEvent.date.asc()).first_or_404("Camp session not found or not a camp.")

    kid = Kid.query.get_or_404(kid_id)
    camp_activity_definition = Activity.query.get_or_404(master_event.activity_id)

    form = EditCampSessionForm()

    if request.method == 'GET':
        actual_session_start_date = get_camp_session_start_date(master_event)
        form.session_start_date.data = actual_session_start_date
        form.session_end_date.data = master_event.camp_session_end_date

        # Determine the cost:
        # If the master_event is the actual first day, use its cost.
        # Otherwise, find the event record that holds the cost for this session.
        if master_event.date == actual_session_start_date:
            form.session_cost.data = master_event.cost
        else:
            cost_event = ScheduledEvent.query.filter(
                ScheduledEvent.kid_id == kid_id,
                ScheduledEvent.camp_session_identifier == camp_session_id,
                ScheduledEvent.cost > 0  # Correct way to filter for cost > 0
            ).first()
            form.session_cost.data = cost_event.cost if cost_event else 0.0

        form.session_is_overnight.data = master_event.is_overnight_camp
        # Notes: Assuming common notes are on the master_event (first day record fetched)
        # or you might need to query for the actual first day record if master_event could be any day.
        # Since master_event IS the first day record by its definition earlier, this is fine.
        form.session_notes.data = master_event.notes

    if form.validate_on_submit():
        new_start_date = form.session_start_date.data
        new_end_date = form.session_end_date.data
        new_cost = form.session_cost.data if form.session_cost.data is not None else 0.0
        new_is_overnight = form.session_is_overnight.data
        new_notes = form.session_notes.data

        # --- Complex Update Logic ---
        # 1. Get all existing daily events for this session
        existing_daily_events = ScheduledEvent.query.filter_by(
            kid_id=kid_id,
            camp_session_identifier=camp_session_id
        ).order_by(ScheduledEvent.date.asc()).all()

        # 2. Determine dates to add, dates to delete, dates to potentially update
        existing_dates = {event.date for event in existing_daily_events}
        required_dates = set()
        current_d = new_start_date
        while current_d <= new_end_date:
            required_dates.add(current_d)
            current_d += timedelta(days=1)

        dates_to_delete_events_for = existing_dates - required_dates
        dates_to_add_events_for = required_dates - existing_dates
        dates_to_keep_events_for = existing_dates.intersection(required_dates)

        events_to_be_deleted_ids = [event.id for event in existing_daily_events if event.date in dates_to_delete_events_for]

        # 3. Conflict check for new/updated date range (excluding current session's events that might be kept/modified)
        # This is tricky. We need to check if *newly added days* or *significantly shifted existing days* cause conflicts.
        # For simplicity, let's check conflicts for all 'required_dates'.
        potential_conflicts_found = False
        for req_date in sorted(list(required_dates)): # Check in order
            # Define daily start/end times for this required_date
            daily_s_time = time(9,0) # Or from camp_activity_definition.default_camp_start_time
            daily_e_time = (datetime.combine(req_date, daily_s_time) + timedelta(minutes=camp_activity_definition.duration_minutes)).time()
            if new_is_overnight:
                if req_date == new_start_date: daily_e_time = time(23,59,59)
                elif req_date == new_end_date: daily_s_time = time(0,0,0)
                else: daily_s_time, daily_e_time = time(0,0,0), time(23,59,59)

            conflict = ScheduledEvent.query.filter(
                ScheduledEvent.kid_id == kid_id,
                ScheduledEvent.date == req_date,
                ScheduledEvent.start_time < daily_e_time,
                ScheduledEvent.end_time > daily_s_time,
                ScheduledEvent.camp_session_identifier != camp_session_id # Exclude events from THIS session
            ).first()
            if conflict:
                flash(f"Conflict on {req_date.strftime('%Y-%m-%d')} with '{conflict.activity_details.name}'. Camp session update aborted.", 'error')
                potential_conflicts_found = True
                break

        if potential_conflicts_found:
            return render_template('schedule/edit_camp_session.html', form=form, activity_name=camp_activity_definition.name, kid=kid, original_start_date=get_camp_session_start_date(master_event))

        # 4. Proceed with modifications if no conflicts found
        # Delete events for dates no longer in the session
        if events_to_be_deleted_ids:
            ScheduledEvent.query.filter(ScheduledEvent.id.in_(events_to_be_deleted_ids)).delete(synchronize_session=False)

        # Update existing events or create new ones
        final_session_events = [] # To find the new first day for cost
        for req_date in sorted(list(required_dates)):
            event_for_this_date = next((e for e in existing_daily_events if e.date == req_date), None)

            daily_s_time = time(9,0) # Or from camp_activity_definition
            daily_e_time = (datetime.combine(req_date, daily_s_time) + timedelta(minutes=camp_activity_definition.duration_minutes)).time()
            if new_is_overnight:
                if req_date == new_start_date: daily_e_time = time(23,59,59)
                elif req_date == new_end_date: daily_s_time = time(0,0,0)
                else: daily_s_time, daily_e_time = time(0,0,0), time(23,59,59)

            if event_for_this_date: # Update existing
                event_for_this_date.start_time = daily_s_time
                event_for_this_date.end_time = daily_e_time
                event_for_this_date.is_overnight_camp = new_is_overnight
                event_for_this_date.notes = new_notes # Apply common notes
                event_for_this_date.camp_session_end_date = new_end_date # Update overall session end date
                event_for_this_date.cost = 0 # Reset cost, will be applied to new first day
                db.session.add(event_for_this_date)
                final_session_events.append(event_for_this_date)
            else: # Create new event for this date
                new_daily_event = ScheduledEvent(
                    kid_id=kid_id, activity_id=camp_activity_definition.id, date=req_date,
                    start_time=daily_s_time, end_time=daily_e_time, status="Scheduled (Camp)",
                    notes=new_notes, is_camp=True, cost=0, # Cost applied later
                    is_overnight_camp=new_is_overnight, camp_session_identifier=camp_session_id,
                    camp_session_end_date=new_end_date
                )
                db.session.add(new_daily_event)
                final_session_events.append(new_daily_event)

        # Apply cost to the new first day of the session
        if final_session_events:
            final_session_events.sort(key=lambda x: x.date) # Ensure sorted by date
            final_session_events[0].cost = new_cost
            # If cost was on an event that got deleted, this re-assigns it.
            # If cost was on an event that is kept but is no longer the first, it gets zeroed above.

        try:
            db.session.commit()
            flash(f"Camp session '{camp_activity_definition.name}' for {kid.name} updated.", 'success')
            return redirect(url_for('schedule.view_day_schedule', date=new_start_date.strftime('%Y-%m-%d'), kid_id=kid.id))
        except Exception as e:
            db.session.rollback(); print(f"Error updating camp session: {e}")
            flash(f"Error updating camp session: {str(e)}", "error")

    # For GET request or if form validation failed on POST
    original_start = get_camp_session_start_date(master_event) if master_event else date.today()
    if form.errors and request.method == 'POST':
        for field, error_list in form.errors.items():
            for error in error_list: flash(f"Error in {getattr(form, field).label.text if hasattr(getattr(form, field), 'label') else field}: {error}", 'danger')

    return render_template('schedule/edit_camp_session.html', form=form,
                           activity_name=camp_activity_definition.name, kid=kid,
                           original_start_date=original_start)

# Reminder: All /api/... routes are in schedule_api_routes.py