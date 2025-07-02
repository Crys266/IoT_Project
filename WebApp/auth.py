"""
Authentication module for IoT RC Car webapp
Provides session-based authentication with secure password hashing
"""

import bcrypt
import secrets
from functools import wraps
from flask import session, request, jsonify, redirect, url_for
from typing import Optional


def hash_password(password: str) -> str:
    """
    Hash password using bcrypt with salt
    """
    salt = bcrypt.gensalt(rounds=12)
    password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
    return password_hash.decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify password against hash
    """
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except Exception as e:
        print(f"❌ Error verifying password: {e}")
        return False


def login_user(username: str, db) -> bool:
    """
    Log in user and create session
    """
    try:
        session['user_id'] = username
        session['logged_in'] = True
        session.permanent = True
        
        # Update last login in database
        db.update_user_login(username)
        print(f"✅ User logged in: {username}")
        return True
    except Exception as e:
        print(f"❌ Error logging in user: {e}")
        return False


def logout_user() -> bool:
    """
    Log out user and clear session
    """
    try:
        session.pop('user_id', None)
        session.pop('logged_in', None)
        session.clear()
        print("✅ User logged out")
        return True
    except Exception as e:
        print(f"❌ Error logging out user: {e}")
        return False


def is_authenticated() -> bool:
    """
    Check if current user is authenticated
    """
    return session.get('logged_in', False) and session.get('user_id') is not None


def get_current_user() -> Optional[str]:
    """
    Get current logged-in username
    """
    if is_authenticated():
        return session.get('user_id')
    return None


def require_auth(f):
    """
    Decorator to require authentication for routes
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_authenticated():
            if request.is_json:
                return jsonify(error="Authentication required"), 401
            else:
                return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def create_default_admin_user(db, username: str = "admin", password: str = "admin123") -> bool:
    """
    Create default admin user if no users exist
    """
    try:
        if db.get_user_count() == 0:
            password_hash = hash_password(password)
            db.create_user(username, password_hash)
            print(f"✅ Default admin user created: {username}")
            print(f"🔐 Default password: {password}")
            print("⚠️ Please change the default password after first login!")
            return True
        return False
    except Exception as e:
        print(f"❌ Error creating default admin user: {e}")
        return False