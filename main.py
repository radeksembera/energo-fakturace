# -*- coding: utf-8 -*-
from flask import Flask, render_template, redirect
import os

# Nastav UTF-8 kódování
os.environ['PYTHONIOENCODING'] = 'utf-8'

# Import models a database
from models import db

# Import Blueprint
from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.strediska import strediska_bp
from routes.ceny import ceny_bp
from routes.fakturace import fakturace_bp
from routes.odecty import odecty_bp
from routes.print import print_bp

from session_helpers import (
    get_session_obdobi, 
    set_session_obdobi, 
    handle_obdobi_selection,
    handle_obdobi_from_rok_mesic
)

# Load environment variables
from dotenv import load_dotenv
if os.path.exists('.env'):
    load_dotenv()

# Flask app configuration
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "tajny_klic")

# Database configuration
# Priorita: DATABASE_URL (produkce) → SQLALCHEMY_DATABASE_URI (lokálně)
database_url = os.environ.get("DATABASE_URL") or os.environ.get("SQLALCHEMY_DATABASE_URI")
if database_url and database_url.startswith("postgres://"):
    # Oprava pro Heroku/Railway starý formát
    database_url = database_url.replace("postgres://", "postgresql://", 1)

# Fallback pro SQLite v produkci (pokud není DATABASE_URL)
if not database_url:
    database_url = "sqlite:///instance/energo_fakturace.db"

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# PostgreSQL connection pool settings to prevent disconnections
if database_url and database_url.startswith("postgresql://"):
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,  # Validate connections before use
        'pool_recycle': 300,    # Recycle connections after 5 minutes
        'pool_size': 10,        # Connection pool size
        'max_overflow': 20      # Additional connections allowed
    }

# Initialize database
db.init_app(app)

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(strediska_bp)
app.register_blueprint(ceny_bp, url_prefix="/strediska")
app.register_blueprint(fakturace_bp, url_prefix="/strediska")
app.register_blueprint(odecty_bp, url_prefix="/strediska")
app.register_blueprint(print_bp, url_prefix="/faktury")

# Template filters and functions
from utils.helpers import safe_sum_filter
from session_helpers import get_obdobi_display_name
app.jinja_env.filters['safe_sum'] = safe_sum_filter
app.jinja_env.globals['get_obdobi_display_name'] = get_obdobi_display_name

@app.route("/")
def index():
    return redirect("/strediska")

# Error handlers
@app.before_request
def log_request_info():
    from flask import request
    print(f"Request: {request.method} {request.url}")

@app.errorhandler(Exception)
def handle_exception(e):
    print(f"Exception: {str(e)}")
    return f"Chyba: {str(e)}", 500

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    
    # Development server
    if os.environ.get("FLASK_ENV") == "development":
        app.run(debug=True, host="0.0.0.0", port=5000)
    else:
        # Production
        app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))