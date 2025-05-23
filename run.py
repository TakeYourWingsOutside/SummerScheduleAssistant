from app import create_app, db # We will create this 'create_app' function soon
from app.models import Kid, Activity, ScheduledEvent # And these models

app = create_app()


# This allows you to use 'flask shell' and have these available
@app.shell_context_processor
def make_shell_context():
    return {'db': db, 'Kid': Kid, 'Activity': Activity, 'ScheduledEvent': ScheduledEvent}


if __name__ == '__main__':
    app.run(debug=True)