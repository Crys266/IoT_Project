from flask import Flask, request, Response, render_template, jsonify, send_from_directory, session, redirect, url_for, \
    flash
import cv2
import numpy as np
from queue import Queue
from object_detection import detect_objects_with_boxes
import time
import threading
import os
from datetime import datetime
from telegram_bot import notify_if_danger, register_chat_id, unregister_chat_id
import tempfile
from io import BytesIO

# Import MongoDB database
from database import create_surveillance_db

# Import authentication
from auth import AuthManager, login_required, generate_secret_key

app = Flask(__name__)

# Configurazione sicura per sessioni
app.secret_key = generate_secret_key()
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 3600

# Queue per frame
frame_queue = Queue(maxsize=1)
detection_frame_queue = Queue(maxsize=1)

# Stato globale
negative_effect = False
object_detection = False
current_command = ""
last_gps = {"lat": None, "lon": None}
last_env = {"temperature": None, "humidity": None}

# Detection system
latest_detection = None
detection_lock = threading.Lock()
detection_count = 0
MAX_DETECTION_AGE = 1.5

# Configurazione colori
red_classes_config = ['person']

# Setup MongoDB
try:
    db = create_surveillance_db()
    print("✅ MongoDB database with GridFS initialized successfully!")
except Exception as e:
    print(f"❌ FATAL: Failed to initialize MongoDB: {e}")
    print("💥 App cannot start without MongoDB connection!")
    exit(1)

# AuthManager
auth_manager = None

# Global variables for FR4
latest_frame = None


def init_auth():
    global auth_manager
    auth_manager = AuthManager(db)
    print("🔐 Authentication system ready!")


def apply_current_effects_to_image(img_data):
    try:
        img_array = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img is None:
            print("❌ Failed to decode image for effects")
            return img_data

        print(f"🎨 Applying effects: negative={negative_effect}, detection={object_detection}")
        detection_applied = False

        if object_detection and latest_detection:
            with detection_lock:
                current_time = time.time()
                if (latest_detection and
                        current_time - latest_detection['timestamp'] <= MAX_DETECTION_AGE):
                    boxes = latest_detection.get('boxes', [])
                    if boxes:
                        print(f"🔍 Applying detection: {len(boxes)} objects")
                        img = draw_detection_boxes_on_live_frame(img, boxes)
                        detection_applied = True

        if negative_effect:
            print("🌗 Applying negative effect")
            img = cv2.bitwise_not(img)

        ret, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if ret:
            print(f"✅ Effects applied successfully (detection: {detection_applied}, negative: {negative_effect})")
            return buffer.tobytes()
        else:
            print("❌ Failed to encode processed image")
            return img_data

    except Exception as e:
        print(f"❌ Error applying effects to image: {e}")
        return img_data


def draw_detection_boxes_on_live_frame(live_img, boxes_data):
    overlay_img = live_img.copy()
    for box in boxes_data:
        x, y, w, h = box['x'], box['y'], box['w'], box['h']
        label = box['label']
        confidence = box['confidence']
        color = (0, 0, 255) if label in red_classes_config else (0, 255, 0)
        cv2.rectangle(overlay_img, (x, y), (x + w, y + h), color, 4)
        label_text = f"{label} {confidence:.2f}"
        font_scale = 0.7
        text_thickness = 2
        (label_w, label_h), baseline = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, text_thickness)
        center_x = x + w // 2
        text_x = center_x - label_w // 2
        text_y = y - 10
        if text_y - label_h < 0:
            text_y = y + h + label_h + 10
        padding = 6
        cv2.rectangle(overlay_img,
                      (text_x - padding, text_y - label_h - padding),
                      (text_x + label_w + padding, text_y + padding),
                      color, -1)
        cv2.rectangle(overlay_img,
                      (text_x - padding, text_y - label_h - padding),
                      (text_x + label_w + padding, text_y + padding),
                      (255, 255, 255), 2)
        cv2.putText(overlay_img, label_text, (text_x, text_y),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), text_thickness)
    return overlay_img


def realtime_detection_worker():
    global latest_detection, detection_count, last_gps
    print("🔍 REALTIME detection worker - ONLY LATEST!")
    print(f"⚡ Max age: {MAX_DETECTION_AGE}s - poi SCARTA!")
    while True:
        try:
            if object_detection:
                frame_data = None
                try:
                    frame_data = detection_frame_queue.get(timeout=0.05)
                    detection_count += 1
                except:
                    time.sleep(0.01)
                    continue
                if frame_data:
                    t0 = time.time()
                    try:
                        img_array = np.frombuffer(frame_data, np.uint8)
                        original_img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                        if original_img is not None:
                            detected_img, real_boxes = detect_objects_with_boxes(original_img)
                            t1 = time.time()
                            with detection_lock:
                                latest_detection = {
                                    'boxes': real_boxes,
                                    'timestamp': t1,
                                    'count': detection_count,
                                    'processing_time': t1 - t0
                                }
                            gps_str = "unknown"
                            if last_gps["lat"] is not None and last_gps["lon"] is not None:
                                gps_str = f"{last_gps['lat']:.6f},{last_gps['lon']:.6f}"

                            # FIX: Gestione corretta file temporaneo su Windows
                            temp_path = None
                            try:
                                # Crea file temporaneo
                                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                                    temp_path = tmp_file.name

                                # Salva immagine
                                cv2.imwrite(temp_path, detected_img)

                                # Chiudi file esplicitamente prima di usarlo
                                tmp_file.close()

                                # Verifica esistenza
                                if os.path.exists(temp_path):
                                    print(f"📸 Saved temp image: {temp_path}")
                                    notify_if_danger(real_boxes, gps=gps_str, image_path=temp_path)
                                else:
                                    print(f"❌ Temp file not found: {temp_path}")

                            except Exception as temp_error:
                                print(f"❌ Temp file error: {temp_error}")
                            finally:
                                # Cleanup sicuro
                                if temp_path and os.path.exists(temp_path):
                                    try:
                                        time.sleep(0.1)  # Piccola pausa per Windows
                                        os.remove(temp_path)
                                        print(f"🧹 Cleaned temp file: {temp_path}")
                                    except Exception as cleanup_error:
                                        print(f"⚠️ Cleanup warning: {cleanup_error}")
                                        # Non bloccare per errori di cleanup

                            if detection_count % 20 == 0:
                                print(f"⚡ LATEST #{detection_count}: {len(real_boxes)} objects in {(t1 - t0):.3f}s")
                    except Exception as e:
                        print(f"❌ LATEST detection error: {e}")
            else:
                with detection_lock:
                    latest_detection = None
                time.sleep(0.1)
        except Exception as e:
            print(f"💥 LATEST detection worker error: {e}")
        time.sleep(0.005)


detection_thread = threading.Thread(target=realtime_detection_worker, daemon=True)
detection_thread.start()


# ============== ROUTES AUTENTICAZIONE ==============

@app.route('/login', methods=['GET', 'POST'])
def login():
    print(f"🔐 Login route called - Method: {request.method}")
    if request.method == 'POST':
        action = request.form.get('action')
        print(f"🔐 Action received: {action}")
        if action == 'login':
            username = request.form.get('username')
            password = request.form.get('password')
            remember = request.form.get('remember')
            print(f"🔐 Login attempt - Username: {username}")
            try:
                user = auth_manager.verify_password(username, password)
                print(f"🔐 Password verification result: {user is not None}")
                if user:
                    session['username'] = username
                    session['user_id'] = str(user['_id'])
                    if remember:
                        session.permanent = True
                    print(f"🔐 Session created for user: {username}")
                    flash('Login effettuato con successo!', 'success')
                    return redirect('/')
                else:
                    print("🔐 Invalid credentials")
                    flash('Username o password non validi!', 'error')
            except Exception as e:
                print(f"🔐 Login error: {e}")
                flash(f'Errore durante il login: {str(e)}', 'error')
        elif action == 'change':
            current_username = request.form.get('current_username')
            current_password = request.form.get('current_password')
            new_username = request.form.get('new_username')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            if new_password and new_password != confirm_password:
                flash('Le password non coincidono!', 'error')
            elif not new_username and not new_password:
                flash('Devi fornire almeno un nuovo username o una nuova password!', 'error')
            else:
                try:
                    result = auth_manager.change_credentials(
                        current_username,
                        current_password,
                        new_username or None,
                        new_password or None
                    )
                    if result['success']:
                        flash(result['message'], 'success')
                        if session.get('username') == current_username and new_username:
                            session['username'] = new_username
                    else:
                        flash(result['message'], 'error')
                except Exception as e:
                    flash(f'Errore durante la modifica: {str(e)}', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Logout effettuato con successo!', 'info')
    return redirect(url_for('login'))


# ============== ROUTES PRINCIPALI ==============

@app.route('/')
@login_required
def index():
    print(f"🏠 Index route called - Session: {dict(session)}")
    return render_template('index.html',
                           gps=last_gps,
                           env=last_env,
                           username=session.get('username'))


@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('favicon.ico')


# ============== ROUTES PUBBLICHE (NO AUTH) ==============

@app.route('/video_feed')
def video_feed():
    """Video feed pubblico per monitoraggio"""
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/upload', methods=['POST'])
def upload():
    """Upload ESP32 - deve rimanere pubblico"""
    global latest_frame, last_env
    img_data = request.data
    latest_frame = img_data
    if frame_queue.full():
        frame_queue.get()
    frame_queue.put(img_data)
    if object_detection:
        while not detection_frame_queue.empty():
            try:
                detection_frame_queue.get_nowait()
            except:
                break
        try:
            detection_frame_queue.put_nowait(img_data)
        except:
            pass
    gps_header = request.headers.get('X-GPS')
    temp_combined = request.headers.get('X-TEMP')
    if temp_combined:
        try:
            temp, hum = map(float, temp_combined.strip().split(","))
            last_env["temperature"] = temp
            last_env["humidity"] = hum
        except:
            pass
    global last_gps
    if gps_header:
        try:
            lat, lon = map(float, gps_header.strip().split(","))
            last_gps = {"lat": lat, "lon": lon}
        except:
            pass
    return "OK", 200


@app.route('/list_saved_images', methods=['GET'])
def list_saved_images():
    """Lista immagini - pubblico per visualizzazione"""
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    filters = {}
    if request.args.get('has_detection') == 'true':
        filters['has_detection'] = True
    if request.args.get('date_from'):
        filters['date_from'] = request.args.get('date_from')
    if request.args.get('date_to'):
        filters['date_to'] = request.args.get('date_to')
    try:
        result = db.get_images_paginated(page=page, limit=limit, filters=filters)
        result['database'] = 'mongodb_gridfs'
        return jsonify(result)
    except Exception as e:
        print(f"❌ MongoDB query failed: {e}")
        return jsonify(error="Database connection failed"), 500


@app.route('/saved_images/<filename>')
def serve_saved_image(filename):
    """Serve immagini da GridFS tramite filename"""
    try:
        print(f"🖼️ Serving image: {filename}")

        # Trova metadati dell'immagine tramite filename
        image_doc = db.images.find_one({"filename": filename})
        if not image_doc:
            print(f"❌ Image document not found: {filename}")
            return "Image not found", 404

        gridfs_image_id = str(image_doc["gridfs_image_id"])
        print(f"📁 GridFS image ID: {gridfs_image_id}")

        # Recupera immagine da GridFS
        image_data, metadata = db.get_image_from_gridfs(gridfs_image_id)
        print(f"✅ Retrieved image: {len(image_data)} bytes")

        return Response(
            image_data,
            mimetype=metadata.get('content_type', 'image/jpeg'),
            headers={
                'Content-Disposition': f'inline; filename="{metadata["filename"]}"',
                'Content-Length': str(len(image_data)),
                'Cache-Control': 'public, max-age=3600'  # Cache per 1 ora
            }
        )

    except Exception as e:
        print(f"❌ Error serving image {filename}: {e}")
        import traceback
        traceback.print_exc()
        return "Error loading image", 500


@app.route('/thumbnails/<filename>')
def serve_thumbnail(filename):
    """Serve thumbnails da GridFS"""
    try:
        print(f"🖼️ Serving thumbnail: {filename}")

        # Rimuovi prefisso "thumb_" se presente per trovare l'immagine originale
        original_filename = filename.replace("thumb_", "") if filename.startswith("thumb_") else filename
        print(f"🔍 Looking for original: {original_filename}")

        # Trova metadati dell'immagine
        image_doc = db.images.find_one({"filename": original_filename})
        if not image_doc:
            print(f"❌ Image document not found for thumbnail: {original_filename}")
            return "Thumbnail not found", 404

        gridfs_thumbnail_id = str(image_doc["gridfs_thumbnail_id"])
        print(f"📁 GridFS thumbnail ID: {gridfs_thumbnail_id}")

        # Recupera thumbnail da GridFS
        thumbnail_data, metadata = db.get_thumbnail_from_gridfs(gridfs_thumbnail_id)
        print(f"✅ Retrieved thumbnail: {len(thumbnail_data)} bytes")

        return Response(
            thumbnail_data,
            mimetype=metadata.get('content_type', 'image/jpeg'),
            headers={
                'Content-Disposition': f'inline; filename="{metadata["filename"]}"',
                'Content-Length': str(len(thumbnail_data)),
                'Cache-Control': 'public, max-age=3600'  # Cache per 1 ora
            }
        )

    except Exception as e:
        print(f"❌ Error serving thumbnail {filename}: {e}")
        import traceback
        traceback.print_exc()
        return "Error loading thumbnail", 500


@app.route('/gps', methods=['GET'])
def gps():
    """GPS pubblico per monitoring"""
    return jsonify(last_gps)


@app.route('/sensor_data', methods=['GET'])
def sensor_data():
    """Dati sensori pubblici per monitoring"""
    return jsonify({
        "temp": last_env.get("temperature"),
        "humi": last_env.get("humidity")
    })


@app.route('/status_data', methods=['GET'])
def status_data():
    """Status pubblico per monitoring"""
    return jsonify({
        "gps": last_gps,
        "env": last_env,
        "database": "mongodb_gridfs"
    })


# ============== ROUTES PROTETTE (CON AUTH) ==============

@app.route('/save_image', methods=['POST'])
@login_required
def save_image():
    global latest_frame, last_gps, last_env
    if latest_frame is None:
        return jsonify(error="No frame available to save"), 400

    try:
        print(f"💾 Saving image with effects to GridFS: negative={negative_effect}, detection={object_detection}")

        # Applica effetti all'immagine
        processed_frame = apply_current_effects_to_image(latest_frame)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        filename = f"captured_{timestamp}.jpg"

        # Prepara metadati per GridFS
        gps_str = "unknown"
        if last_gps["lat"] is not None and last_gps["lon"] is not None:
            gps_str = f"{last_gps['lat']:.6f},{last_gps['lon']:.6f}"

        image_record = {
            'filename': filename,
            'size': len(processed_frame),
            'created': datetime.now().isoformat(),
            'gps': gps_str,
            'gps_lat': last_gps["lat"],
            'gps_lon': last_gps["lon"],
            'temperature': last_env.get("temperature"),
            'humidity': last_env.get("humidity"),
            'tags': [],
            'description': '',
            'analysis': None,
            'detection_active': object_detection,
            'negative_effect': negative_effect,
            'effects_applied': {
                'negative': negative_effect,
                'object_detection': object_detection
            },
            'saved_by': session.get('username')
        }

        # Aggiungi detection results se presenti
        detection_objects_count = 0
        if object_detection and latest_detection:
            with detection_lock:
                if latest_detection and time.time() - latest_detection['timestamp'] <= MAX_DETECTION_AGE:
                    detection_objects_count = len(latest_detection['boxes'])

                    def sanitize_box(box):
                        return {
                            'x': int(box['x']),
                            'y': int(box['y']),
                            'w': int(box['w']),
                            'h': int(box['h']),
                            'label': str(box['label']),
                            'confidence': float(box['confidence'])
                        }

                    sanitized_boxes = [sanitize_box(b) for b in latest_detection['boxes']]
                    image_record['detection_results'] = {
                        'boxes': sanitized_boxes,
                        'detection_time': float(latest_detection['timestamp']),
                        'processing_time': float(latest_detection['processing_time']),
                        'objects_count': int(detection_objects_count)
                    }

        # Salva in GridFS (immagine + thumbnail + metadati)
        try:
            image_id = db.save_image_metadata(processed_frame, image_record)
            image_record['mongodb_id'] = image_id
            print(f"✅ Image saved to GridFS with ID: {image_id}")
        except Exception as e:
            print(f"❌ GridFS save failed: {e}")
            return jsonify(error=f"GridFS save failed: {str(e)}"), 500

        effects_info = []
        if negative_effect:
            effects_info.append("negative")
        if object_detection and detection_objects_count > 0:
            effects_info.append(f"detection({detection_objects_count} objects)")
        elif object_detection:
            effects_info.append("detection(no objects)")

        print(f"📸 Image saved to GridFS: {filename} (GPS: {gps_str}) by {session.get('username')}")

        return jsonify(
            status="success",
            image=image_record,
            effects_applied=effects_info,
            database="mongodb_gridfs",
            storage="GridFS"
        )

    except Exception as e:
        print(f"❌ Error saving image to GridFS: {e}")
        return jsonify(error=f"Failed to save image: {str(e)}"), 500


@app.route('/delete_image/<image_id>', methods=['DELETE'])
@login_required
def delete_image(image_id):
    try:
        # Cerca immagine in MongoDB
        images_result = db.get_images_paginated(limit=1000)
        image = None
        for img in images_result['images']:
            if str(img['id']) == str(image_id):
                image = img
                break

        if not image:
            return jsonify(error="Image not found"), 404

        # Elimina da GridFS (anche thumbnail)
        if db.delete_image(image_id):
            print(f"🗑️ Deleted image from GridFS: {image['filename']} by {session.get('username')}")
            return jsonify(status="success", message=f"Image {image['filename']} deleted from GridFS")
        else:
            return jsonify(error="Failed to delete from GridFS"), 500

    except Exception as e:
        print(f"❌ Error deleting image from GridFS: {e}")
        return jsonify(error=f"Failed to delete image: {str(e)}"), 500


@app.route('/update_image/<image_id>', methods=['POST'])
@login_required
def update_image_metadata(image_id):
    data = request.json
    try:
        updates = {}
        if 'tags' in data:
            updates['tags'] = data['tags']
        if 'description' in data:
            updates['description'] = data['description']
        updates['updated_by'] = session.get('username')
        updates['updated'] = datetime.now().isoformat()
        if db.update_image_metadata(image_id, updates):
            return jsonify(status="success", database="mongodb_gridfs")
        else:
            return jsonify(error="Failed to update image"), 500
    except Exception as e:
        print(f"❌ GridFS update error: {e}")
        return jsonify(error=f"Update failed: {str(e)}"), 500


@app.route('/send_image_telegram/<image_id>', methods=['POST'])
@login_required
def send_image_telegram(image_id):
    try:
        # Cerca immagine in MongoDB
        images_result = db.get_images_paginated(limit=1000)
        image = None
        for img in images_result['images']:
            if str(img['id']) == str(image_id):
                image = img
                break
        if not image:
            return jsonify(error="Image not found"), 404

        # Recupera immagine da GridFS
        gridfs_image_id = image['gridfs_image_id']
        image_data, metadata = db.get_image_from_gridfs(gridfs_image_id)

        # Salva temporaneamente per Telegram
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
            tmp_file.write(image_data)
            temp_path = tmp_file.name

        label_info = ""
        if image.get('detection_results'):
            detected = image['detection_results']
            label_info = f"\nOggetti: {', '.join([b['label'] for b in detected['boxes']])}"
        gps_str = image.get('gps', 'unknown')
        caption = f"Immagine dalla gallery GridFS (inviata da {session.get('username')}).{label_info}"

        def send_and_cleanup():
            try:
                notify_if_danger([], gps_str, temp_path, caption=caption)
            finally:
                os.remove(temp_path)

        threading.Thread(target=send_and_cleanup, daemon=True).start()
        return jsonify(status="sent", storage="GridFS")
    except Exception as e:
        return jsonify(error=str(e)), 500


@app.route('/control', methods=['POST'])
@login_required
def control():
    global current_command
    direction = request.form.get('direction')
    current_command = direction
    print(f"🎮 COMANDO RICEVUTO: {direction} da {session.get('username')}")
    return jsonify(status="command received", direction=direction)


@app.route('/toggle_negative', methods=['POST'])
@login_required
def toggle_negative():
    global negative_effect
    negative_effect = not negative_effect
    print(f"🎨 Negative: {'ON' if negative_effect else 'OFF'} da {session.get('username')}")
    return jsonify(status="negative effect toggled", negative_effect=negative_effect)


@app.route('/toggle_object_detection', methods=['POST'])
@login_required
def toggle_object_detection():
    global object_detection, latest_detection
    object_detection = not object_detection
    if not object_detection:
        with detection_lock:
            latest_detection = None
        while not detection_frame_queue.empty():
            try:
                detection_frame_queue.get_nowait()
            except:
                break
        print(f"🔍 REALTIME detection: OFF da {session.get('username')}")
    else:
        print(f"🔍 REALTIME detection: ON - max age {MAX_DETECTION_AGE}s da {session.get('username')}")
    return jsonify(status="object detection toggled", object_detection=object_detection)


@app.route('/set_red_classes', methods=['POST'])
@login_required
def set_red_classes():
    global red_classes_config
    classes = request.form.get('classes', 'person').split(',')
    classes = [c.strip() for c in classes if c.strip()]
    red_classes_config = classes
    print(f"🔴 Red classes updated: {classes} da {session.get('username')}")
    return jsonify(status="red classes updated", red_classes=classes)


@app.route('/set_max_age', methods=['POST'])
@login_required
def set_max_age():
    global MAX_DETECTION_AGE
    age = request.form.get('age', type=float)
    if age and 0.1 <= age <= 3.0:
        MAX_DETECTION_AGE = age
        print(f"⏰ Max detection age: {age}s da {session.get('username')}")
        return jsonify(status="max age updated", max_age=MAX_DETECTION_AGE)
    return jsonify(error="Invalid age (0.1-3.0s)"), 400


# ============== ROUTES MONGODB AVANZATE (PROTETTE) ==============

@app.route('/images/near/<float:lat>/<float:lon>')
@login_required
def images_near_location(lat, lon):
    """Trova immagini vicine a coordinate specifiche"""
    radius_km = request.args.get('radius', 1.0, type=float)
    try:
        images = db.find_images_near_location(lat, lon, radius_km)
        return jsonify({
            "images": images,
            "query": {"lat": lat, "lon": lon, "radius_km": radius_km},
            "count": len(images),
            "database": "mongodb_gridfs"
        })
    except Exception as e:
        return jsonify(error=f"Geospatial query failed: {str(e)}"), 500


@app.route('/statistics/detection')
@login_required
def detection_statistics():
    """Statistiche avanzate su object detection"""
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    date_range = (date_from, date_to) if date_from and date_to else None
    try:
        stats = db.get_detection_statistics(date_range)
        stats['database'] = 'mongodb_gridfs'
        return jsonify(stats)
    except Exception as e:
        return jsonify(error=f"Statistics query failed: {str(e)}"), 500


@app.route('/database/stats')
@login_required
def database_stats():
    """Statistiche del database per monitoring"""
    try:
        stats = db.get_database_stats()
        stats['database'] = 'mongodb_gridfs'
        return jsonify(stats)
    except Exception as e:
        return jsonify(error=f"Database stats failed: {str(e)}"), 500


# ============== ROUTES RESTANTI ==============

@app.route('/get_command', methods=['GET'])
def get_command():
    """ESP32 polling - deve rimanere pubblico"""
    global current_command
    print(f"📤 ESP32 CHIEDE: {current_command}")
    return current_command


# ============== FRAME GENERATION ==============

def gen_frames():
    frame_count = 0
    while True:
        t0 = time.time()
        frame = frame_queue.get()
        frame_count += 1
        img_array = np.frombuffer(frame, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if negative_effect:
            img = cv2.bitwise_not(img)
        if object_detection:
            with detection_lock:
                current_time = time.time()
                if (latest_detection and
                        current_time - latest_detection['timestamp'] <= MAX_DETECTION_AGE):
                    boxes = latest_detection.get('boxes', [])
                    count = latest_detection.get('count', '?')
                    age = current_time - latest_detection['timestamp']
                    processing_time = latest_detection.get('processing_time', 0)
                    if boxes:
                        img = draw_detection_boxes_on_live_frame(img, boxes)
                    if age < 0.3:
                        status_color = (0, 255, 0)
                    elif age < 1.0:
                        status_color = (255, 255, 0)
                    else:
                        status_color = (255, 165, 0)
                    cv2.putText(img, f"LIVE + LATEST #{count} (age: {age:.2f}s)",
                                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 2)
                    red_count = len([b for b in boxes if b['label'] in red_classes_config])
                    green_count = len(boxes) - red_count
                    cv2.putText(img, f"🔴 {red_count} person  🟢 {green_count} objects",
                                (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, status_color, 2)
                    cv2.putText(img, f"Process: {processing_time:.3f}s | Max age: {MAX_DETECTION_AGE}s",
                                (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.4, status_color, 2)
                else:
                    cv2.putText(img, "LIVE VIDEO - REALTIME MODE",
                                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
                    cv2.putText(img, f"Waiting for objects... #{detection_count}",
                                (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)
                    cv2.putText(img, f"Max age: {MAX_DETECTION_AGE}s (GridFS Storage)",
                                (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 2)
        ret, buffer = cv2.imencode('.jpg', img)
        t1 = time.time()
        frame_time = round((t1 - t0) * 1000)
        if frame_count % 300 == 0:
            fps = 1000 / max(frame_time, 1)
            print(f"[LIVE #{frame_count}] {frame_time}ms (~{fps:.1f}fps) | GridFS Storage")
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


# ============== TELEGRAM WEBHOOK ==============

@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    """Telegram webhook - pubblico"""
    data = request.json
    if not data: return "no data"
    message = data.get("message") or data.get("edited_message")
    if message:
        chat_id = message["chat"]["id"]
        text = message.get("text", "")
        if text.lower().startswith("/stop"):
            unregister_chat_id(chat_id)
            from telegram_bot import send_telegram_message
            send_telegram_message("❌ Disiscritto: non riceverai più notifiche.", chat_id)
        else:
            register_chat_id(chat_id)
            if text.lower().startswith("/start"):
                from telegram_bot import send_telegram_message
                send_telegram_message(
                    "✅ Benvenuto! Riceverai notifiche automatiche dal sistema.\nPer disattivarle invia /stop.", chat_id)
    return "ok"


# ============== STARTUP ==============

if __name__ == '__main__':
    init_auth()
    print("🚀 Flask ESP32-CAM with MongoDB GridFS ONLY + Authentication System")
    print("🔐 Login required for RC car controls")
    print("📹 Video: Live stream with ZERO accumulation")
    print("🔍 Detection: ONLY LATEST - no old results!")
    print(f"⚡ Max detection age: {MAX_DETECTION_AGE}s")
    print("🔴 RED: person | 🟢 GREEN: all other objects")
    print("📍 Labels: ABOVE boxes, horizontally centered")
    print("⚡ REALTIME MODE: Scarta tutto il vecchio!")
    print("📸 FR4: Image saving with GridFS storage!")
    print("🤖 Telegram Bot: Multi-user notifications enabled")
    print("🔒 Authentication: Session-based with bcrypt password hashing")
    print("🗄️ GridFS: Complete file storage in MongoDB")

    # Database status
    try:
        stats = db.get_database_stats()
        images_count = stats.get('images_collection', {}).get('count', 0)
        gridfs_files = stats.get('gridfs', {}).get('images_files', 0)
        print(f"📊 Images in MongoDB: {images_count}")
        print(f"📁 GridFS files: {gridfs_files}")
    except:
        print("📊 MongoDB stats not available")

    print("🆕 GridFS endpoints:")
    print("  - GET/POST /save_image - Saves to GridFS")
    print("  - GET /saved_images/<filename> - Serves from GridFS")
    print("  - GET /thumbnails/<filename> - Serves thumbnails from GridFS")
    print("  - DELETE /delete_image/<id> - Deletes from GridFS")
    print("✅ GridFS-only system active (no filesystem dependencies)")
    print("🔐 Default login: admin / admin123 (change after first login!)")

    app.run(host='0.0.0.0', port=5000, debug=True)
