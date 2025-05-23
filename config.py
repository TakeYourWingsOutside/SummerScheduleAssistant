import os
from dotenv import load_dotenv

# Load environment variables from .env file (optional, but good practice)
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-super-secret-key-that-you-should-change'
    # For SQLite:
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
                              'sqlite:///' + os.path.join(basedir, 'app.db')
    # For PostgreSQL (example, if you switch later):
    # SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
    #    'postgresql://user:password@host:port/database_name'

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Add other configurations here if needed
