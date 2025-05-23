from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from config import Config

db = SQLAlchemy()
migrate = Migrate()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)

    # Import models HERE.
    from . import models # Use relative import

    migrate.init_app(app, db)

    # Import and register blueprints
    # Ensure these files exist and define 'bp'
    from app.routes.main_routes import bp as main_bp
    app.register_blueprint(main_bp)

    from app.routes.activity_routes import bp as activity_bp
    app.register_blueprint(activity_bp, url_prefix='/activities')

    from app.routes.schedule_routes import bp as schedule_bp
    app.register_blueprint(schedule_bp, url_prefix='/schedule')

    # New API schedule routes
    from app.routes.schedule_api_routes import bp_api as schedule_api_bp # New blueprint instance
    app.register_blueprint(schedule_api_bp) # url_prefix is '/schedule/api' defined in the blueprint

    from app.routes.export_routes import bp as export_bp
    app.register_blueprint(export_bp)

    from app.routes.report_routes import bp as report_bp # NEW
    app.register_blueprint(report_bp) # url_prefix is '/reports' defined in blueprint

    from . import commands
    commands.register_commands(app)

    from datetime import datetime

    @app.context_processor
    def inject_now():
        return {'now': datetime.utcnow()}

    return app
