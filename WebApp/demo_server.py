#!/usr/bin/env python3
"""
Demo server to showcase login interface without MongoDB requirement
"""

from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import secrets
from datetime import timedelta

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
app.permanent_session_lifetime = timedelta(days=30)

# Demo user credentials
DEMO_USER = {
    'username': 'admin',
    'password': 'admin123'
}

@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('index.html', current_user=session.get('user_id', 'admin'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == DEMO_USER['username'] and password == DEMO_USER['password']:
            session['logged_in'] = True
            session['user_id'] = username
            session.permanent = True
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Invalid username or password")
    
    return render_template('login.html')

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('login'))

# Mock video feed for demo
@app.route('/video_feed')
def video_feed():
    return "Video feed would be here (ESP32-CAM stream)"

if __name__ == '__main__':
    print("🚀 Demo Server - Login Interface Showcase")
    print("📋 Credentials: admin / admin123")
    print("🌐 Access: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)