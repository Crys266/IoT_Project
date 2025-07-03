from functools import wraps
from flask import session, request, redirect, url_for, flash
import bcrypt
from datetime import datetime
import secrets


class AuthManager:
    def __init__(self, db):
        self.db = db
        self.users_collection = db.db['users']
        self._ensure_admin_user()

    def _ensure_admin_user(self):
        """Crea utente admin di default se non esiste"""
        admin_user = self.users_collection.find_one({"username": "admin"})
        if not admin_user:
            default_password = "admin123"  # Password di default che può essere cambiata
            password_hash = bcrypt.hashpw(default_password.encode('utf-8'), bcrypt.gensalt(rounds=12))

            self.users_collection.insert_one({
                "username": "admin",
                "password_hash": password_hash,
                "created_at": datetime.now(),
                "last_login": None,
                "is_active": True
            })
            print("🔐 Default admin user created (username: admin, password: admin123)")
            print("⚠️  Please change the default password after first login!")

    def verify_password(self, username, password):
        """Verifica username e password"""
        user = self.users_collection.find_one({"username": username, "is_active": True})
        if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash']):
            # Aggiorna ultimo login
            self.users_collection.update_one(
                {"_id": user["_id"]},
                {"$set": {"last_login": datetime.now()}}
            )
            return user
        return None

    def change_credentials(self, current_username, current_password, new_username=None, new_password=None):
        """Cambia username e/o password"""
        # Verifica credenziali attuali
        user = self.verify_password(current_username, current_password)
        if not user:
            return {"success": False, "message": "Credenziali attuali non valide"}

        updates = {}

        # Cambia username se fornito
        if new_username and new_username != current_username:
            # Controlla se il nuovo username esiste già
            existing = self.users_collection.find_one({"username": new_username})
            if existing:
                return {"success": False, "message": "Username già esistente"}
            updates["username"] = new_username

        # Cambia password se fornita
        if new_password:
            if len(new_password) < 6:
                return {"success": False, "message": "La password deve essere almeno 6 caratteri"}
            password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt(rounds=12))
            updates["password_hash"] = password_hash

        if not updates:
            return {"success": False, "message": "Nessuna modifica fornita"}

        # Applica modifiche
        self.users_collection.update_one(
            {"_id": user["_id"]},
            {"$set": updates}
        )

        # Aggiorna sessione se username è cambiato
        if "username" in updates:
            session['username'] = new_username

        return {"success": True, "message": "Credenziali aggiornate con successo"}

    def get_user_info(self, username):
        """Ottieni informazioni utente"""
        user = self.users_collection.find_one(
            {"username": username, "is_active": True},
            {"password_hash": 0}  # Escludi hash password
        )
        return user


def login_required(f):
    """Decorator per route che richiedono autenticazione"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        print(f"🔒 Login check for route: {request.endpoint}")
        print(f"🔒 Session contents: {dict(session)}")
        print(f"🔒 Username in session: {session.get('username')}")

        if 'username' not in session:
            print("🔒 No username in session - redirecting to login")
            flash('Devi effettuare il login per accedere a questa pagina', 'warning')
            return redirect('/login')  # Usa redirect diretto

        print(f"🔒 Access granted for user: {session.get('username')}")
        return f(*args, **kwargs)

    return decorated_function


def generate_secret_key():
    """Genera chiave segreta per sessioni Flask"""
    return secrets.token_hex(32)