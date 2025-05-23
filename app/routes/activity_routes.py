from flask import Blueprint, render_template, redirect, url_for, flash, request
from app import db
from app.models import Activity, Kid, ScheduledEvent # Kid model is needed for form.kids_assigned
from app.forms import ActivityForm # ActivityForm now includes camp definition fields

bp = Blueprint('activities', __name__) # url_prefix='/activities' is in app/__init__.py

@bp.route('/')
def list_activities():
    activities = Activity.query.order_by(Activity.is_camp_activity.desc(), Activity.name).all()

    print("--- DEBUG: list_activities route ---")
    print(f"Total activities fetched: {len(activities)}")
    for act in activities:
        print(f"Name: {act.name}, ID: {act.id}, is_camp_activity: {act.is_camp_activity} (Type: {type(act.is_camp_activity)})")
    print("--- END DEBUG ---")

    return render_template('activities/list.html', activities=activities)

@bp.route('/add', methods=['GET', 'POST'])
def add_activity():
    form = ActivityForm()
    if form.validate_on_submit():
        activity = Activity(
            name=form.name.data,
            description=form.description.data,
            duration_minutes=form.duration_minutes.data,
            requires_supervision=form.requires_supervision.data,
            requires_another_person=form.requires_another_person.data,
            can_do_alone=form.can_do_alone.data,
            requires_transportation=form.requires_transportation.data,

            # Camp definition fields
            is_camp_activity=form.is_camp_activity.data,
            # Only set camp-specific defaults if it IS a camp definition
            default_camp_cost=form.default_camp_cost.data if form.is_camp_activity.data else None,
            default_is_overnight=form.default_is_overnight.data if form.is_camp_activity.data else False
            # Add default_camp_start_time, default_camp_end_time if you implemented them in the form/model
        )

        # Handle kids_assigned (eligible kids for this activity/camp type)
        selected_kid_ids = form.kids_assigned.data
        activity.kids_assigned = [] # Clear first, then append
        for kid_id in selected_kid_ids:
            kid = Kid.query.get(kid_id)
            if kid:
                activity.kids_assigned.append(kid)

        db.session.add(activity)
        try:
            db.session.commit()
            flash(f"Definition for '{activity.name}' added successfully!", 'success')
            return redirect(url_for('activities.list_activities'))
        except Exception as e:
            db.session.rollback()
            # Log the full error for debugging
            print(f"ERROR in add_activity commit: {str(e)}")
            flash(f"Error adding definition: Could not save to database. Check server logs.", 'error')

    # For GET request or if form validation failed
    if form.errors:
        for field, error_list in form.errors.items():
            for error in error_list:
                flash(f"Error in {getattr(form, field).label.text}: {error}", 'danger') # Use danger for Bootstrap

    return render_template('activities/form.html', form=form, title="Add New Activity/Camp Definition")

@bp.route('/edit/<int:activity_id>', methods=['GET', 'POST'])
def edit_activity(activity_id):
    activity = Activity.query.get_or_404(activity_id)
    form = ActivityForm(obj=activity) # Pre-populate form with existing activity data

    if request.method == 'GET':
        # Pre-select assigned kids when loading the form for editing
        form.kids_assigned.data = [kid.id for kid in activity.kids_assigned]
        # Ensure camp fields are correctly populated from the object if it is a camp
        # WTForms obj=activity should handle this, but explicit can be clearer or a fallback
        if activity.is_camp_activity:
            form.is_camp_activity.data = True
            form.default_camp_cost.data = activity.default_camp_cost
            form.default_is_overnight.data = activity.default_is_overnight
            # Pre-populate default_camp_start_time, default_camp_end_time if used
        else:
            form.is_camp_activity.data = False # Ensure it's unchecked if not a camp

    if form.validate_on_submit():
        activity.name = form.name.data
        activity.description = form.description.data
        activity.duration_minutes = form.duration_minutes.data
        activity.requires_supervision = form.requires_supervision.data
        activity.requires_another_person = form.requires_another_person.data
        activity.can_do_alone = form.can_do_alone.data
        activity.requires_transportation = form.requires_transportation.data

        activity.is_camp_activity = form.is_camp_activity.data
        if activity.is_camp_activity: # If it's marked as a camp definition
            activity.default_camp_cost = form.default_camp_cost.data
            activity.default_is_overnight = form.default_is_overnight.data
            # Set default_camp_start_time, default_camp_end_time if used
        else: # If it's NOT a camp definition, nullify camp-specific defaults
            activity.default_camp_cost = None
            activity.default_is_overnight = False
            # Set default_camp_start_time = None, default_camp_end_time = None if used

        # Update kids_assigned
        activity.kids_assigned = [] # Clear existing associations first
        selected_kid_ids = form.kids_assigned.data
        for kid_id in selected_kid_ids:
            kid = Kid.query.get(kid_id)
            if kid:
                activity.kids_assigned.append(kid)

        try:
            db.session.commit()
            flash(f"Definition for '{activity.name}' updated successfully!", 'success')
            return redirect(url_for('activities.list_activities'))
        except Exception as e:
            db.session.rollback()
            print(f"ERROR in edit_activity commit: {str(e)}")
            flash(f"Error updating definition: Could not save to database. Check server logs.", 'error')

    if form.errors and request.method == 'POST': # Only flash errors if it was a POST attempt
        for field, error_list in form.errors.items():
            for error in error_list:
                flash(f"Error in {getattr(form, field).label.text}: {error}", 'danger')

    return render_template('activities/form.html', form=form, title="Edit Activity/Camp Definition", activity_id=activity_id)

@bp.route('/delete/<int:activity_id>', methods=['POST'])
def delete_activity(activity_id):
    activity = Activity.query.get_or_404(activity_id)
    activity_name = activity.name # Get name before deleting

    # Before deleting an Activity definition, consider implications for ScheduledEvents
    # that might be linked to it.
    # Option 1: Cascade delete (if setup in model, ScheduledEvent.activity_id would be set to NULL or event deleted)
    # Option 2: Prevent deletion if linked to scheduled events.
    # Current ScheduledEvent model has: activity_id = db.Column(db.Integer, db.ForeignKey('activity.id'), nullable=False)
    # So, deleting an Activity will likely cause an IntegrityError if ScheduledEvents reference it,
    # unless the ForeignKey constraint has ON DELETE SET NULL or ON DELETE CASCADE (not default).
    # For now, let's check and prevent deletion if it's in use.

    if activity.scheduled_events.first(): # Check if any scheduled events use this activity
        flash(f"Cannot delete '{activity_name}' because it is currently used in scheduled events. Please remove it from all schedules first.", 'danger')
        return redirect(url_for('activities.list_activities'))

    try:
        # If we reach here, no scheduled events are using this activity definition.
        # Clear M2M with Kids before deleting the activity itself
        activity.kids_assigned = []
        db.session.delete(activity)
        db.session.commit()
        flash(f"Definition '{activity_name}' deleted successfully!", 'success')
    except Exception as e:
        db.session.rollback()
        print(f"ERROR in delete_activity: {str(e)}")
        flash(f"Error deleting definition '{activity_name}': {str(e)}", 'error')

    return redirect(url_for('activities.list_activities'))


@bp.route('/clear_all_definitions', methods=['POST']) # POST for destructive action
def clear_all_activity_definitions():
    # IMPORTANT: This is highly destructive. It will delete ALL activity and camp definitions.
    # It will FAIL if any of these definitions are currently linked to ScheduledEvent records
    # due to the ForeignKey constraint (Activity.id in ScheduledEvent.activity_id is NOT NULL).

    # Check if any activities are in use before attempting to delete all
    activities_in_use = db.session.query(ScheduledEvent.activity_id).distinct().all()
    if activities_in_use:
        # Get names of activities in use for a more informative message (optional, can be slow if many)
        # used_activity_ids = [item[0] for item in activities_in_use]
        # used_activities = Activity.query.filter(Activity.id.in_(used_activity_ids)).all()
        # used_names = [act.name for act in used_activities[:5]] # Show first 5
        # flash(f"Cannot clear all definitions. Some are in use by scheduled events (e.g., {', '.join(used_names)}{'...' if len(used_names) < len(used_activity_ids) else ''}). Please clear the schedule first or remove these activities from schedules.", 'danger')

        flash(f"Cannot clear all definitions. {len(activities_in_use)} type(s) of activities/camps are currently in use in scheduled events. Please clear the schedule or remove these specific definitions from all schedules first.", 'danger')
        return redirect(url_for('activities.list_activities'))

    try:
        # If we reach here, no activities are currently scheduled.
        # We still need to clear the M2M relationship with Kids for each activity.
        all_activities = Activity.query.all()
        for activity_def in all_activities:
            activity_def.kids_assigned = [] # Clear M2M link
        # No commit needed here for M2M clear if cascade handles it on delete, but safer.
        # db.session.commit()

        num_deleted = db.session.query(Activity).delete()
        db.session.commit()
        flash(f"Successfully cleared {num_deleted} activity/camp definition(s).", 'success')
        print(f"INFO: All activity definitions cleared by user action. Count: {num_deleted}")
    except Exception as e:
        db.session.rollback()
        flash(f"Error clearing activity definitions: {str(e)}", 'error')
        print(f"ERROR: Failed to clear all activity definitions: {str(e)}")

    return redirect(url_for('activities.list_activities'))