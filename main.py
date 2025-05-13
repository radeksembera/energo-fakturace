from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os

from models import db, User, Stredisko

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "tajny_klic")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Pokud spouštíš lokálně, můžeš použít create_all (na serveru to nedělej!)
with app.app_context():
    db.create_all()

@app.route("/")
def index():
    if not session.get("user_id"):
        return redirect("/login")
    return redirect("/strediska")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            session["username"] = user.username
            return redirect("/strediska")
        return render_template("login.html", error="Neplatné přihlášení.")


    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/strediska")
def strediska():
    if not session.get("user_id"):
        return redirect("/login")
    strediska = Stredisko.query.filter_by(user_id=session["user_id"]).all()
    return render_template("strediska.html", strediska=strediska)

@app.route("/admin/users", methods=["GET", "POST"])
def admin_users():
    if not session.get("user_id"):
        return redirect("/login")
    user = User.query.get(session["user_id"])
    if not user or user.username != "admin":
        return redirect("/login")

    if request.method == "POST":
        username = request.form["username"]
        password_hash = generate_password_hash(request.form["password"])
        new_user = User(username=username, password_hash=password_hash)
        db.session.add(new_user)
        db.session.commit()

    users = User.query.order_by(User.id).all()
    return render_template("admin_users.html", users=users)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
