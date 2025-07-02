from flask import Flask, request, Response, render_template, jsonify, send_from_directory
import cv2
import numpy as np
from queue import Queue
from object_detection import detect_objects_with_boxes
import time
import threading
import os
import json
from datetime import datetime
from telegram_bot import notify_if_danger, register_chat_id, unregister_chat_id
import tempfile

# NUOVO: Import MongoDB database
from database import create_surveillance_db

app = Flask(__name__)

# Queue per frame
frame_queue = Queue(maxsize=1)
detection_frame_queue = Queue(maxsize=1)  # SOLO 1 frame alla volta

# Stato globale
negative_effect = False
object_detection = False
current_command = ""
last_gps = {"lat": None, "lon": None}
last_env = {"temperature": None, "humidity": None}

# Detection system "ONLY LATEST" - DURATA AUMENTATA
latest_detection = None
detection_lock = threading.Lock()
detection_count = 0
MAX_DETECTION_AGE = 1.5  # AUMENTATO: 1.5 secondi invece di 0.5!

# Configurazione colori
red_classes_config = ['person']

# NUOVO: Setup MongoDB invece di JSON
try:
    db = create_surveillance_db()
    print("✅ MongoDB database initialized successfully!")
except Exception as e:
    print(f"❌ Failed to initialize MongoDB: {e}")
    print("💡 Falling back to JSON system...")
    db = None

# FR4: Image management setup
SAVED_IMAGES_DIR = "saved_images"
THUMBNAILS_DIR = os.path.join(SAVED_IMAGES_DIR, "thumbnails")
METADATA_FILE = os.path.join(SAVED_IMAGES_DIR, "images_database.json")

# Create directories
for directory in [SAVED_IMAGES_DIR, THUMBNAILS_DIR]:
    if not os.path.exists(directory):
        os.makedirs(directory)

# Global variables for FR4
latest_frame = None





# NUOVO: Migrazione automatica da JSON se MongoDB è disponibile
def migrate_existing_data():
    """Migra dati esistenti da JSON a MongoDB se necessario"""
    if db is None:
        return

    json_file = METADATA_FILE
    if os.path.exists(json_file):
        print("🔄 Found existing JSON database, starting migration...")
        result = db.migrate_from_json(json_file)

        if result["status"] == "success":
            print(f"✅ Migration completed: {result['migrated_count']}/{result['total_items']} items")
            if result["errors"]:
                print(f"⚠️ Migration errors: {len(result['errors'])}")

            # Backup del file JSON
            backup_file = json_file + f".backup_{int(time.time())}"
            os.rename(json_file, backup_file)
            print(f"📦 JSON file backed up to: {backup_file}")
        else:
            print(f"❌ Migration failed: {result['message']}")


def create_thumbnail(image_path, thumbnail_path, size=(150, 150)):
    try:
        img = cv2.imread(image_path)
        if img is not None:
            h, w = img.shape[:2]
            aspect = w / h
            if aspect > 1:
                new_w, new_h = size[0], int(size[0] / aspect)
            else:
                new_w, new_h = int(size[1] * aspect), size[1]
            resized = cv2.resize(img, (new_w, new_h))
            cv2.imwrite(thumbnail_path, resized)
            return True
    except Exception as e:
        print(f"❌ Error creating thumbnail: {e}")
    return False


    # Setup complete - verify MongoDB connection
    if db is None:
        print("❌ MongoDB is required for this application to function!")
        print("💡 Please ensure MongoDB is running and accessible")
        print("🔗 Default connection: mongodb://localhost:27017/")
        exit(1)
    else:
        # Auto-migrate existing JSON data if available
        migrate_existing_data()


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
                    else:
                        print("🔍 No detection boxes to apply")
                else:
                    print(
                        f"🔍 Detection too old: age={current_time - latest_detection['timestamp'] if latest_detection else 'N/A'}s")
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
                            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                                temp_path = tmp_file.name
                                cv2.imwrite(temp_path, detected_img)
                                print("Salvato alert image in:", temp_path, "esiste?", os.path.exists(temp_path))
                                notify_if_danger(real_boxes, gps=gps_str, image_path=temp_path)
                                os.remove(temp_path)
                            if detection_count % 20 == 0:
                                print(
                                    f"⚡ LATEST #{detection_count}: {len(real_boxes)} objects in {(t1 - t0):.3f}s (age limit: {MAX_DETECTION_AGE}s)")
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


@app.route('/')
def index():
    return render_template('index.html', gps=last_gps, env=last_env)


@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('favicon.ico')


@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


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
                    cv2.putText(img, f"Max age: {MAX_DETECTION_AGE}s (INCREASED)",
                                (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 2)
        ret, buffer = cv2.imencode('.jpg', img)
        t1 = time.time()
        frame_time = round((t1 - t0) * 1000)
        if frame_count % 300 == 0:
            fps = 1000 / max(frame_time, 1)
            print(
                f"[LIVE #{frame_count}] {frame_time}ms (~{fps:.1f}fps) | REALTIME mode | Detection age limit: {MAX_DETECTION_AGE}s")
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


@app.route('/upload', methods=['POST'])
def upload():
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


@app.route('/save_image', methods=['POST'])
def save_image():
    global latest_frame, last_gps, last_env
    if latest_frame is None:
        return jsonify(error="No frame available to save"), 400

    try:
        print(f"💾 Saving image with effects: negative={negative_effect}, detection={object_detection}")
        processed_frame = apply_current_effects_to_image(latest_frame)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        filename = f"captured_{timestamp}.jpg"
        filepath = os.path.join(SAVED_IMAGES_DIR, filename)
        thumbnail_path = os.path.join(THUMBNAILS_DIR, f"thumb_{filename}")

        # Salva file fisico
        with open(filepath, 'wb') as f:
            f.write(processed_frame)
        create_thumbnail(filepath, thumbnail_path)

        # Prepara metadati
        gps_str = "unknown"
        if last_gps["lat"] is not None and last_gps["lon"] is not None:
            gps_str = f"{last_gps['lat']:.6f},{last_gps['lon']:.6f}"

        image_record = {
            'filename': filename,
            'filepath': filepath,
            'thumbnail': f"thumb_{filename}",
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
            }
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

        # Save to MongoDB (required)
        try:
            image_id = db.save_image_metadata(image_record)
            image_record['mongodb_id'] = image_id
            print(f"✅ Image saved to MongoDB with ID: {image_id}")
            database_used = "mongodb"
        except Exception as e:
            print(f"❌ Failed to save image to MongoDB: {e}")
            return jsonify(error=f"Database save failed: {str(e)}"), 500

        effects_info = []
        if negative_effect:
            effects_info.append("negative")
        if object_detection and detection_objects_count > 0:
            effects_info.append(f"detection({detection_objects_count} objects)")
        elif object_detection:
            effects_info.append("detection(no objects)")

        print(f"📸 Image saved: {filename} (GPS: {gps_str}) [DB: {database_used}]")

        return jsonify(
            status="success",
            image=image_record,
            effects_applied=effects_info,
            database=database_used
        )

    except Exception as e:
        print(f"❌ Error saving image: {e}")
        return jsonify(error=f"Failed to save image: {str(e)}"), 500


@app.route('/list_saved_images', methods=['GET'])
def list_saved_images():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)

    # Filtri opzionali
    filters = {}
    if request.args.get('has_detection') == 'true':
        filters['has_detection'] = True
    if request.args.get('date_from'):
        filters['date_from'] = request.args.get('date_from')
    if request.args.get('date_to'):
        filters['date_to'] = request.args.get('date_to')

    try:
        result = db.get_images_paginated(page=page, limit=limit, filters=filters)
        result['database'] = 'mongodb'
        return jsonify(result)
    except Exception as e:
        print(f"❌ MongoDB query failed: {e}")
        return jsonify(error=f"Database query failed: {str(e)}"), 500


@app.route('/delete_image/<image_id>', methods=['DELETE'])
def delete_image(image_id):
    try:
        # Get image details first
        images_result = db.get_images_paginated(limit=1000)
        image = None
        for img in images_result['images']:
            if img['id'] == image_id:
                image = img
                break

        if not image:
            return jsonify(error="Image not found"), 404

        # Delete physical files
        if os.path.exists(image['filepath']):
            os.remove(image['filepath'])
        thumbnail_path = os.path.join(THUMBNAILS_DIR, image['thumbnail'])
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)

        # Delete from MongoDB
        if db.delete_image(image_id):
            print(f"🗑️ Deleted image from MongoDB: {image['filename']}")
            return jsonify(status="success", message=f"Image {image['filename']} deleted", database="mongodb")
        else:
            return jsonify(error="Failed to delete from MongoDB"), 500
    except Exception as e:
        print(f"❌ Error deleting image: {e}")
        return jsonify(error=f"Failed to delete image: {str(e)}"), 500


@app.route('/update_image/<image_id>', methods=['POST'])
def update_image_metadata(image_id):
    data = request.json

    try:
        updates = {}
        if 'tags' in data:
            updates['tags'] = data['tags']
        if 'description' in data:
            updates['description'] = data['description']

        if db.update_image_metadata(image_id, updates):
            return jsonify(status="success", database="mongodb")
        else:
            return jsonify(error="Failed to update image metadata"), 500
    except Exception as e:
        print(f"❌ MongoDB update error: {e}")
        return jsonify(error=f"Database update failed: {str(e)}"), 500


@app.route('/saved_images/<filename>')
def serve_saved_image(filename):
    return send_from_directory(SAVED_IMAGES_DIR, filename)


@app.route('/thumbnails/<filename>')
def serve_thumbnail(filename):
    return send_from_directory(THUMBNAILS_DIR, filename)


# NUOVO: Endpoint per funzionalità avanzate MongoDB
@app.route('/images/near/<float:lat>/<float:lon>')
def images_near_location(lat, lon):
    """Trova immagini vicine a coordinate specifiche"""
    if db is None:
        return jsonify(error="MongoDB not available for geospatial queries"), 503

    radius_km = request.args.get('radius', 1.0, type=float)

    try:
        images = db.find_images_near_location(lat, lon, radius_km)
        return jsonify({
            "images": images,
            "query": {"lat": lat, "lon": lon, "radius_km": radius_km},
            "count": len(images),
            "database": "mongodb"
        })
    except Exception as e:
        return jsonify(error=f"Geospatial query failed: {str(e)}"), 500


@app.route('/statistics/detection')
def detection_statistics():
    """Statistiche avanzate su object detection"""
    if db is None:
        return jsonify(error="MongoDB not available for advanced statistics"), 503

    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    date_range = (date_from, date_to) if date_from and date_to else None

    try:
        stats = db.get_detection_statistics(date_range)
        stats['database'] = 'mongodb'
        return jsonify(stats)
    except Exception as e:
        return jsonify(error=f"Statistics query failed: {str(e)}"), 500


@app.route('/database/stats')
def database_stats():
    """Statistiche del database per monitoring"""
    if db is None:
        return jsonify(error="MongoDB not available"), 503

    try:
        stats = db.get_database_stats()
        stats['database'] = 'mongodb'
        return jsonify(stats)
    except Exception as e:
        return jsonify(error=f"Database stats failed: {str(e)}"), 500


@app.route('/send_image_telegram/<image_id>', methods=['POST'])
def send_image_telegram(image_id):
    try:
        images_result = db.get_images_paginated(limit=1000)
        image = None
        for img in images_result['images']:
            if str(img['id']) == str(image_id):
                image = img
                break

        if not image:
            return jsonify(error="Image not found"), 404

        path = image['filepath']
        label_info = ""
        if image.get('detection_results'):
            detected = image['detection_results']
            label_info = f"\nOggetti: {', '.join([b['label'] for b in detected['boxes']])}"
        gps_str = image.get('gps', 'unknown')
        threading.Thread(
            target=notify_if_danger,
            args=([], gps_str, path),
            kwargs={'image_path': path, 'caption': f"Immagine dalla gallery.{label_info}"}
        ).start()
        return jsonify(status="sent")
    except Exception as e:
        print(f"❌ Error sending image to telegram: {e}")
        return jsonify(error=f"Failed to send image: {str(e)}"), 500


@app.route('/toggle_negative', methods=['POST'])
def toggle_negative():
    global negative_effect
    negative_effect = not negative_effect
    print(f"🎨 Negative: {'ON' if negative_effect else 'OFF'}")
    return jsonify(status="negative effect toggled", negative_effect=negative_effect)


@app.route('/toggle_object_detection', methods=['POST'])
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
        print("🔍 REALTIME detection: OFF")
    else:
        print(f"🔍 REALTIME detection: ON - max age {MAX_DETECTION_AGE}s")
    return jsonify(status="object detection toggled", object_detection=object_detection)


@app.route('/set_red_classes', methods=['POST'])
def set_red_classes():
    global red_classes_config
    classes = request.form.get('classes', 'person').split(',')
    classes = [c.strip() for c in classes if c.strip()]
    red_classes_config = classes
    print(f"🔴 Red classes updated: {classes}")
    return jsonify(status="red classes updated", red_classes=classes)


@app.route('/set_max_age', methods=['POST'])
def set_max_age():
    global MAX_DETECTION_AGE
    age = request.form.get('age', type=float)
    if age and 0.1 <= age <= 3.0:
        MAX_DETECTION_AGE = age
        print(f"⏰ Max detection age: {age}s")
        return jsonify(status="max age updated", max_age=MAX_DETECTION_AGE)
    return jsonify(error="Invalid age (0.1-3.0s)"), 400


@app.route('/control', methods=['POST'])
def control():
    global current_command
    direction = request.form.get('direction')
    current_command = direction
    print(f"🎮 COMANDO RICEVUTO: {direction}")
    return jsonify(status="command received", direction=direction)


@app.route('/get_command', methods=['GET'])
def get_command():
    global current_command
    print(f"📤 ESP32 CHIEDE: {current_command}")
    return current_command


@app.route('/status_data', methods=['GET'])
def status_data():
    # For AJAX polling (GPS + ENV)
    return jsonify({
        "gps": last_gps,
        "env": last_env,
        "database": "mongodb" if db is not None else "json"
    })


@app.route('/gps', methods=['GET'])
def gps():
    # For compatibility: returns only GPS
    return jsonify(last_gps)


@app.route('/sensor_data', methods=['GET'])
def sensor_data():
    return jsonify({
        "temp": last_env.get("temperature"),
        "humi": last_env.get("humidity")
    })


# --- TELEGRAM BOT WEBHOOK (multi-user subscribe/unsubscribe) ---
@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
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


if __name__ == '__main__':
    print("🚀 Flask ESP32-CAM with MongoDB + REALTIME Detection + FR4 Image Saving")
    print("📹 Video: Live stream with ZERO accumulation")
    print("🔍 Detection: ONLY LATEST - no old results!")
    print(f"⚡ INCREASED Max detection age: {MAX_DETECTION_AGE}s")
    print("🔴 RED: person | 🟢 GREEN: all other objects")
    print("📍 Labels: ABOVE boxes, horizontally centered")
    print("⚡ REALTIME MODE: Scarta tutto il vecchio!")
    print("📸 FR4: Image saving with effects applied (negative + detection)!")
    print("🤖 Telegram Bot: Multi-user notifications enabled")

    # Database status
    print("✅ MongoDB connection active - JSON fallback system removed")
    try:
        stats = db.get_database_stats()
        images_count = stats.get('images_collection', {}).get('count', 0)
        print(f"📊 Images in MongoDB: {images_count}")
    except:
        print("📊 MongoDB stats not available")
    print("🆕 MongoDB endpoints:")
    print("  - GET /images/near/<lat>/<lon>?radius=1.0 - Geospatial search")
    print("  - GET /statistics/detection - Advanced detection stats")
    print("  - GET /database/stats - Database monitoring")

    app.run(host='0.0.0.0', port=5000, debug=True)
