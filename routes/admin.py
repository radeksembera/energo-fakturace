from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash
from models import db, User
from routes.auth import admin_required
import secrets
import string

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

@admin_bp.route("/users/<int:user_id>/edit", methods=["POST"])
@admin_required
def edit_user_simple(user_id):
    target_user = User.query.get_or_404(user_id)
    
    # Aktualizuj data
    target_user.email = request.form.get("email", "").strip()
    new_password = request.form.get("password", "").strip()
    
    target_user.is_active = 'is_active' in request.form
    
    if new_password:
        target_user.password_hash = generate_password_hash(new_password)
        flash(f"✅ Uživatel {target_user.email} byl aktualizován včetně nového hesla.")
    else:
        flash(f"✅ Uživatel {target_user.email} byl úspěšně aktualizován.")
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"❌ Chyba při ukládání: {str(e)}")
    
    return redirect(url_for("admin.admin_users"))

@admin_bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@admin_required
def reset_password_simple(user_id):
    target_user = User.query.get_or_404(user_id)
    
    # Vygeneruj náhodné heslo
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    new_password = ''.join(secrets.choice(alphabet) for i in range(10))
    
    target_user.password_hash = generate_password_hash(new_password)
    
    try:
        db.session.commit()
        return {
            "success": True, 
            "new_password": new_password,
            "message": f"Heslo pro {target_user.email} bylo resetováno"
        }
    except Exception as e:
        db.session.rollback()
        return {"success": False, "message": str(e)}, 500

@admin_bp.route("/users", methods=["GET", "POST"])
@admin_required
def admin_users():
    # Vytvoření nového uživatele
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        
        if not email or not password:
            flash("❌ Email a heslo jsou povinné.")
            return redirect(url_for("admin.admin_users"))
        
        # Zkontroluj duplicity
        if User.query.filter_by(email=email).first():
            flash("❌ Uživatel s tímto emailem již existuje.")
            return redirect(url_for("admin.admin_users"))
        
        # Vytvoř uživatele
        new_user = User(
            email=email,
            password_hash=generate_password_hash(password)
        )
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash(f"✅ Uživatel {email} byl úspěšně vytvořen.")
        except Exception as e:
            db.session.rollback()
            flash(f"❌ Chyba při vytváření uživatele: {str(e)}")

    # Načti všechny uživatele
    users = User.query.order_by(User.id).all()
    
    return render_template("admin_users_simple.html", users=users)