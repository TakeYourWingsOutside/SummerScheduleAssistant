from app import db
from app.models import Kid, Activity, ScheduledEvent
from datetime import datetime, time, timedelta, date # Ensure 'date' is imported for datetime.combine(date.min, ...)
import random

TARGET_DAILY_MINUTES = int(8 * 60 * 0.80)
DEFAULT_DAY_START_TIME = time(9, 0) # 9:00 AM
# Define a reasonable end time for auto-scheduling to prevent scheduling too late
LATEST_AUTO_SCHEDULE_END_TIME = time(22, 0, 0) # 10 PM

def auto_schedule_day(kid_id, schedule_date):
    # --- Start of Debug Prints ---
    print(f"\n--- DEBUG: auto_schedule_day for kid_id={kid_id}, date={schedule_date} ---")
    # --- End of Debug Prints ---

    kid = Kid.query.get(kid_id)
    if not kid:
        print("DEBUG: Kid not found in auto_schedule_day.")
        return False, "Kid not found."

    existing_events = ScheduledEvent.query.filter_by(kid_id=kid.id, date=schedule_date) \
        .order_by(ScheduledEvent.start_time).all()
    print(f"DEBUG: Found {len(existing_events)} existing events for this day.")

    already_scheduled_minutes = 0
    occupied_slots = [] # List of (start_time, end_time) tuples for existing events
    for event in existing_events:
        if event.activity_details:
            already_scheduled_minutes += event.activity_details.duration_minutes
        occupied_slots.append((event.start_time, event.end_time))
    print(f"DEBUG: Already scheduled minutes: {already_scheduled_minutes}. Target: {TARGET_DAILY_MINUTES}")

    # --- MODIFIED ACTIVITY FILTER ---
    # Fetch all activities assigned to the kid first
    all_assigned_activities = kid.activities.all() # Assuming kid.activities is lazy='dynamic'
    print(f"DEBUG: Total activities assigned to kid '{kid.name}': {len(all_assigned_activities)}")

    available_activities = []
    for act in all_assigned_activities:
        # CRITICAL: Ensure we only consider REGULAR activities (not camp definitions)
        # AND activities that can be done alone or don't require a partner (simplification for auto-scheduler)
        if not act.is_camp_activity and \
                (not act.requires_another_person or act.can_do_alone):
            available_activities.append(act)
        # else: # For debugging which activities are filtered out
        # print(f"DEBUG: Activity '{act.name}' filtered out. is_camp: {act.is_camp_activity}, req_partner: {act.requires_another_person}, can_do_alone: {act.can_do_alone}")

    print(f"DEBUG: Filtered to {len(available_activities)} available REGULAR activities for auto-scheduling.")
    # --- END MODIFIED ACTIVITY FILTER ---

    if not available_activities:
        print("DEBUG: No suitable regular activities found after filtering for auto-scheduling.")
        return False, f"No suitable regular (non-camp) activities found for {kid.name} to auto-schedule."

    random.shuffle(available_activities)

    current_suggested_start_time = DEFAULT_DAY_START_TIME
    # Adjust current_suggested_start_time if there are existing events at the start of the day
    if occupied_slots:
        # Find the end time of the latest event that finishes before or at DEFAULT_DAY_START_TIME,
        # or the earliest event that starts after. This logic can be tricky.
        # Simpler: if any event overlaps DEFAULT_DAY_START_TIME, start after it.
        for start_slot, end_slot in sorted(occupied_slots): # Sort by start time
            if current_suggested_start_time < end_slot and start_slot < (datetime.combine(date.min, DEFAULT_DAY_START_TIME) + timedelta(minutes=1)).time() : # if it overlaps the window around default start
                current_suggested_start_time = end_slot # Move past it

    print(f"DEBUG: Initial current_suggested_start_time set to: {current_suggested_start_time}")


    total_scheduled_today_by_auto = 0
    newly_scheduled_event_objects = [] # Store actual ScheduledEvent objects to add to session

    max_overall_scheduling_attempts = len(available_activities) + 5 # Safety break for main loop
    current_scheduling_attempt = 0

    while total_scheduled_today_by_auto < (TARGET_DAILY_MINUTES - already_scheduled_minutes) and \
            available_activities and current_scheduling_attempt < max_overall_scheduling_attempts:

        current_scheduling_attempt += 1
        print(f"\nDEBUG: Main Scheduling Loop Attempt #{current_scheduling_attempt}. Suggested start: {current_suggested_start_time}. Target remaining: {(TARGET_DAILY_MINUTES - already_scheduled_minutes) - total_scheduled_today_by_auto} mins.")

        # Find the next truly free slot starting from current_suggested_start_time
        actual_slot_start_time = current_suggested_start_time
        slot_found_and_free = False

        temp_occupied_slots_with_new = list(occupied_slots) # Combine existing and newly added for conflict check
        for new_ev_obj in newly_scheduled_event_objects:
            temp_occupied_slots_with_new.append((new_ev_obj.start_time, new_ev_obj.end_time))
        temp_occupied_slots_with_new.sort()


        iteration_to_find_slot = 0
        while iteration_to_find_slot < 100: # Safety break for finding slot
            iteration_to_find_slot+=1
            is_free_at_actual_start = True
            for existing_start, existing_end in temp_occupied_slots_with_new:
                # If actual_slot_start_time falls within an existing_slot, or ends within it
                if actual_slot_start_time < existing_end and \
                        (datetime.combine(date.min, actual_slot_start_time) + timedelta(minutes=1)).time() > existing_start: # checks for overlap of at least 1 min
                    actual_slot_start_time = existing_end # Jump past this occupied slot
                    is_free_at_actual_start = False
                    break
            if is_free_at_actual_start:
                slot_found_and_free = True
                break
            if actual_slot_start_time >= LATEST_AUTO_SCHEDULE_END_TIME:
                break # Stop if we're trying to schedule too late

        if not slot_found_and_free or actual_slot_start_time >= LATEST_AUTO_SCHEDULE_END_TIME:
            print(f"DEBUG: Could not find a free slot after {actual_slot_start_time} or reached scheduling end time limit.")
            break # Break from main while loop

        print(f"DEBUG: Found free slot starting at: {actual_slot_start_time}")

        activity_scheduled_in_this_pass = False
        for i, activity_to_try in enumerate(list(available_activities)): # Iterate copy for safe removal
            print(f"DEBUG:  Trying activity '{activity_to_try.name}' (duration: {activity_to_try.duration_minutes} min) for slot starting {actual_slot_start_time}")

            potential_event_end_time = (datetime.combine(schedule_date, actual_slot_start_time) + \
                                        timedelta(minutes=activity_to_try.duration_minutes)).time()

            if potential_event_end_time > LATEST_AUTO_SCHEDULE_END_TIME:
                print(f"DEBUG:    Activity '{activity_to_try.name}' ends too late ({potential_event_end_time}). Skipping.")
                continue

            # Final conflict check for this specific activity in this specific slot
            # (against all existing and newly added events in this run)
            is_conflict = False
            for es, ee in temp_occupied_slots_with_new:
                if actual_slot_start_time < ee and potential_event_end_time > es:
                    is_conflict = True; break
            if is_conflict:
                print(f"DEBUG:    Conflict found for '{activity_to_try.name}' in slot {actual_slot_start_time}-{potential_event_end_time} (should have been caught by slot finder). Skipping.");
                continue

            # If no conflict, schedule this activity
            new_event = ScheduledEvent(
                kid_id=kid.id, activity_id=activity_to_try.id, date=schedule_date,
                start_time=actual_slot_start_time, end_time=potential_event_end_time,
                status="Scheduled (Auto)",
                is_camp=False, cost=None, is_overnight_camp=False,
                camp_session_identifier=None, camp_session_end_date=None
            )
            newly_scheduled_event_objects.append(new_event)
            available_activities.remove(activity_to_try) # Remove from pool for this auto-schedule run

            total_scheduled_today_by_auto += activity_to_try.duration_minutes
            current_suggested_start_time = potential_event_end_time # Next attempt will start after this
            activity_scheduled_in_this_pass = True
            print(f"DEBUG:  SUCCESS - Scheduled '{activity_to_try.name}' from {actual_slot_start_time} to {potential_event_end_time}. Minutes added: {activity_to_try.duration_minutes}")
            break # Found an activity for this slot, move to next main while loop iteration

        if not activity_scheduled_in_this_pass:
            print(f"DEBUG: No activity from the remaining pool could fit into the slot starting at {actual_slot_start_time}. Advancing suggested start time.")
            # If no activity fit the current free slot, we need to advance current_suggested_start_time
            # to avoid getting stuck trying the same slot. Advance by a small amount.
            # This part is tricky. If the slot itself was too small for any remaining activity.
            # For now, if nothing fits a found free slot, the outer loop's attempt count might break it.
            # A better advance would be to find the end of the *next* occupied slot or just add 15-30 mins.
            # Let's break if no activity could be scheduled in this found free slot.
            # The outer loop will then try to find the next free slot.
            if not available_activities: # No more activities to try
                print("DEBUG: No activities left in the pool.")
                break
            # If activities are left but none fit, the current_suggested_start_time will be the start of the slot
            # that nothing fit into. The next iteration of the main while loop will try finding a new free slot from there.
            # This should be okay.
            print(f"DEBUG: No activity fit the current free slot starting at {actual_slot_start_time}. The main loop will try to find the next slot.")


    if not newly_scheduled_event_objects:
        print("DEBUG: No new events were actually added to the session in this run.")
        if already_scheduled_minutes >= TARGET_DAILY_MINUTES:
            return True, f"Day for {kid.name} is already sufficiently scheduled. No new activities auto-scheduled."
        return False, f"Could not auto-schedule any new regular activities for {kid.name}. Check activity availability, durations, or existing schedule density."

    db.session.add_all(newly_scheduled_event_objects) # Add all collected new events
    try:
        db.session.commit()
        print(f"DEBUG: Successfully committed {len(newly_scheduled_event_objects)} new auto-scheduled events.")
        return True, f"Auto-scheduled {len(newly_scheduled_event_objects)} regular activities for {kid.name} ({total_scheduled_today_by_auto} minutes added)."
    except Exception as e:
        db.session.rollback()
        print(f"ERROR during auto-schedule commit: {e}")
        return False, f"An error occurred while saving auto-scheduled events: {str(e)}"