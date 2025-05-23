import click
import json
import os
from flask.cli import with_appcontext
from . import db
from .models import Kid, Activity, ScheduledEvent
import uuid # For fallback naming if an activity in JSON has no name

def register_commands(app):
    @app.cli.command("init-data")
    @with_appcontext
    def init_data_command():
        """Clears existing data and loads new data from JSON files and predefined kids."""
        click.echo("Attempting to clear existing data...")

        db.session.query(ScheduledEvent).delete(synchronize_session=False)

        all_activities_to_clear_assoc = Activity.query.all()
        if all_activities_to_clear_assoc:
            click.echo(f"Found {len(all_activities_to_clear_assoc)} activities to clear M2M links for.")
            for act_to_clear in all_activities_to_clear_assoc:
                act_to_clear.kids_assigned = []
        else:
            click.echo("No existing activities found to clear M2M links.")

        db.session.query(Activity).delete(synchronize_session=False)
        db.session.query(Kid).delete(synchronize_session=False)

        try:
            db.session.commit()
            click.echo("Successfully committed data clearing.")
        except Exception as e:
            db.session.rollback()
            click.echo(f"Error during data clearing commit: {e}")
            return

        db.session.expire_all()
        click.echo("Cleared existing Kid, Activity, and ScheduledEvent data. Session objects expired.")

        # Add Kids
        kids_json_data = [
            {"name": "Reece", "age": 15},
            {"name": "Silas", "age": 13},
            {"name": "Sofia", "age": 9}
        ]
        session_kids_map = {}
        for kid_info in kids_json_data:
            kid = Kid(name=kid_info["name"], age=kid_info["age"])
            db.session.add(kid)
            session_kids_map[kid.name] = kid
        try:
            db.session.commit()
            click.echo(f"Added/verified {len(session_kids_map)} kids.")
        except Exception as e:
            db.session.rollback(); click.echo(f"Error committing kids: {e}"); return

        # --- Load Activity and Camp Definitions ---
        all_definitions_from_json = []

        activities_file_path = os.path.join(app.root_path, 'data', 'activities.json')
        click.echo(f"Attempting to load regular activities from: {activities_file_path}")
        try:
            with open(activities_file_path, 'r') as f:
                regular_activities_data = json.load(f)
                for item in regular_activities_data:
                    item['is_camp_activity'] = item.get('is_camp_activity', False)
                all_definitions_from_json.extend(regular_activities_data)
                click.echo(f"Loaded {len(regular_activities_data)} definitions from {activities_file_path}.")
        except FileNotFoundError:
            click.echo(f"Warning: Regular activities file not found at {activities_file_path}. Skipping.")
        except json.JSONDecodeError as e:
            click.echo(f"ERROR: Could not decode JSON from {activities_file_path}. Error: {e}")

        camps_file_path = os.path.join(app.root_path, 'data', 'camps.json')
        click.echo(f"Attempting to load camp definitions from: {camps_file_path}")
        try:
            with open(camps_file_path, 'r') as f:
                camp_definitions_data = json.load(f)
                for item in camp_definitions_data:
                    item['is_camp_activity'] = True
                all_definitions_from_json.extend(camp_definitions_data)
                click.echo(f"Loaded {len(camp_definitions_data)} definitions from {camps_file_path}.")
        except FileNotFoundError:
            click.echo(f"Warning: Camp definitions file not found at {camps_file_path}. Skipping.")
        except json.JSONDecodeError as e:
            click.echo(f"ERROR: Could not decode JSON from {camps_file_path}. Error: {e}")

        if not all_definitions_from_json:
            click.echo("No activity or camp definition data found in JSON files to load.")
            click.echo("Database initialization complete (only kids added).")
            return
        # --- End Loading ---

        activities_to_add_to_db = []
        processed_activity_names = set()

        for activity_info in all_definitions_from_json:
            activity_name = activity_info.get("name")
            if not activity_name: # Handle missing name more gracefully
                activity_name = f"Unnamed Activity {uuid.uuid4()}"
                click.echo(f"Warning: Found an activity definition without a name. Assigning temporary name: {activity_name}")

            if activity_name in processed_activity_names:
                click.echo(f"Warning: Duplicate activity name '{activity_name}' found in JSON data. Skipping subsequent entry.")
                continue
            processed_activity_names.add(activity_name)

            is_camp = activity_info.get("is_camp_activity", False)

            activity = Activity(
                name=activity_name,
                description=activity_info.get("description", ""),
                duration_minutes=activity_info.get("duration_minutes", 60),
                requires_supervision=activity_info.get("requires_supervision", False),
                requires_another_person=activity_info.get("requires_another_person", False),
                can_do_alone=activity_info.get("can_do_alone", True),
                requires_transportation=activity_info.get("requires_transportation", False),
                is_camp_activity=is_camp,
                default_camp_cost=(
                    float(activity_info.get("default_camp_cost"))
                    if is_camp and activity_info.get("default_camp_cost") is not None
                    else None
                ),
                default_is_overnight=(
                    activity_info.get("default_is_overnight", False)
                    if is_camp
                    else False
                )
            )

            assigned_kid_names = activity_info.get("kids_assigned", [])
            for kid_name in assigned_kid_names:
                kid_instance = session_kids_map.get(kid_name)
                if kid_instance:
                    if kid_instance not in activity.kids_assigned:
                        activity.kids_assigned.append(kid_instance)
                else:
                    click.echo(f"Warning: Kid '{kid_name}' not found for activity '{activity.name}'.")

            activities_to_add_to_db.append(activity)

        if activities_to_add_to_db:
            db.session.add_all(activities_to_add_to_db)

        try:
            db.session.commit()
            click.echo(f"Successfully processed and committed {len(activities_to_add_to_db)} unique activity/camp definitions.") # Changed count here
        except Exception as e:
            db.session.rollback()
            click.echo(f"Error committing activity/camp definitions: {str(e)}")
            if "unique constraint failed" in str(e).lower() and "activity.name" in str(e).lower():
                click.echo("This error is likely due to duplicate activity names that were not caught by the initial check, or a race condition if names are generated non-uniquely.")
            import traceback
            traceback.print_exc()

        click.echo("Database initialization complete.")

    @app.cli.command("create-tables")
    @with_appcontext
    def create_tables_command():
        """Creates all database tables if they don't exist."""
        db.create_all()
        click.echo("Database tables checked/created.")