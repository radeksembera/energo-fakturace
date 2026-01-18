from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash, generate_password_hash
from models import db, User
from functools import wraps
from datetime import datetime

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        user = db.session.query(User).filter(User.email == email).first()

        print(f"DEBUG: User found: {user}")
        if user:
            print(f"DEBUG: User email: {user.email}")
            print(f"DEBUG: User is_admin: {user.is_admin}")
            print(f"DEBUG: User is_active: {user.is_active}")

        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                return render_template("login.html", error="Váš účet byl deaktivován. Kontaktujte administrátora.")

            # Aktualizace času posledního přihlášení
            user.last_login = datetime.utcnow()
            db.session.commit()

            session["user_id"] = user.id
            session["email"] = user.email
            session["is_admin"] = user.is_admin

            print(f"DEBUG: Session after login: {dict(session)}")
            return redirect("/strediska")
        return render_template("login.html", error="Neplatné přihlášení.")

    return render_template("login.html")

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            return redirect("/login")
        if not session.get("is_admin", False):
            flash("Přístup odmítnut. Vyžaduje se administrátorské oprávnění.", "error")
            return redirect("/strediska")
        return f(*args, **kwargs)
    return decorated_function

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function