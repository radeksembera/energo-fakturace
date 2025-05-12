# main.py

from flask import Flask, render_template, request, redirect, url_for, session
import os
import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)  # ✅ musí být globálně dostupné
app.secret_key = "tajny_klic"

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor)

# ... všechny tvé routy zůstávají stejné ...

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
