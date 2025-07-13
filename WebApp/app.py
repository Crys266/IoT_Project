import asyncio
import websockets
import json
import base64
import threading
import time
from queue import Queue
import cv2
import numpy as np
import os
from datetime import datetime
import tempfile

# Import delle funzionalità esistenti
from object_detection import detect_objects_with_boxes
from telegram_bot import notify_if_danger, register_chat_id, unregister_chat_id, send_telegram_message, \
    send_to_all_chats, telegram_longpoll_bot
from database import create_surveillance_db
from auth import AuthManager, generate_secret_key, login_required

# Setup MongoDB
try:
    db = create_surveillance_db()
    print("✅ MongoDB database with GridFS initialized successfully!")
except Exception as e:
    print(f"❌ FATAL: Failed to initialize MongoDB: {e}")
    exit(1)

threading.Thread(target=telegram_longpoll_bot, daemon=True).start()
print("🤖 Telegram polling bot started in background.")

# Auth Manager
auth_manager = AuthManager(db)

# State globale
connected_clients = {
    'esp32': None,
    'web_clients': {}
}

frame_queue = Queue(maxsize=2)
detection_frame_queue = Queue(maxsize=1)

# Stato sistema
current_command = ""
latest_frame = None
frame_count = 0
last_gps = {"lat": None, "lon": None}
last_env = {"temperature": None, "humidity": None}

# Effetti video - OTTIMIZZATI
negative_effect = False
object_detection = False
latest_detection = None
detection_lock = threading.Lock()
detection_count = 0
MAX_DETECTION_AGE = 0.8  # RIDOTTO da 1.5s a 0.8s per più fluidità
red_classes_config = db.get_dangerous_classes()

# OTTIMIZZAZIONE: Detection più veloce
DETECTION_SKIP_FRAMES = 3  # Processa 1 frame ogni 3 per performance
detection_frame_counter = 0

current_speed = 255


class IoTWebSocketServer:
    def __init__(self, host='0.0.0.0', websocket_port=8765, http_port=5000):
        self.host = host
        self.websocket_port = websocket_port
        self.http_port = http_port

        # Avvia worker per detection ottimizzato
        self.start_detection_worker()

    def start_detection_worker(self):
        """Avvia worker per object detection ottimizzato"""
        detection_thread = threading.Thread(target=self.realtime_detection_worker, daemon=True)
        detection_thread.start()
        print("🔍 Optimized object detection worker started")

    def realtime_detection_worker(self):
        """Worker per object detection real-time SEMPLIFICATO: sempre immagine annotata."""
        global latest_detection, detection_count, last_gps, detection_frame_counter

        while True:
            try:
                if object_detection:
                    frame_data = None
                    try:
                        frame_data = detection_frame_queue.get(timeout=0.02)
                        detection_frame_counter += 1
                    except:
                        time.sleep(0.005)
                        continue

                    # Salta frame per performance
                    if detection_frame_counter % DETECTION_SKIP_FRAMES != 0:
                        continue

                    t0 = time.time()
                    try:
                        img_array = np.frombuffer(frame_data, np.uint8)
                        original_img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                        if original_img is None:
                            continue

                        # Ridimensiona se necessario
                        height, width = original_img.shape[:2]
                        if width > 416:
                            scale = 416 / width
                            new_size = (int(width * scale), int(height * scale))
                            processed_img = cv2.resize(original_img, new_size)
                        else:
                            processed_img = original_img

                        # Detection e annotazione
                        detected_img, real_boxes = detect_objects_with_boxes(processed_img)

                        # Se avevi ridimensionato, riporta i box alle dimensioni originali
                        if width > 416:
                            scale_back = width / processed_img.shape[1]
                            for box in real_boxes:
                                box['x'] = int(box['x'] * scale_back)
                                box['y'] = int(box['y'] * scale_back)
                                box['w'] = int(box['w'] * scale_back)
                                box['h'] = int(box['h'] * scale_back)

                            # Ridisegna i box sull'immagine originale
                            detected_img, _ = detect_objects_with_boxes(original_img)
                        else:
                            # detected_img già sull'immagine originale
                            pass

                        t1 = time.time()

                        # Aggiorna stato detection
                        with detection_lock:
                            latest_detection = {
                                'boxes': real_boxes,
                                'timestamp': t1,
                                'count': detection_count,
                                'processing_time': t1 - t0,
                                'frame_number': detection_frame_counter
                            }

                        detection_count += 1

                        # Applica negativo se attivo
                        if negative_effect:
                            detected_img = cv2.bitwise_not(detected_img)

                        # Salva JPEG annotata in memoria
                        ret, jpeg_bytes = cv2.imencode('.jpg', detected_img)
                        if not ret:
                            continue
                        jpeg_bytes = jpeg_bytes.tobytes()

                        # Notifica Telegram (solo se oggetti rilevati)
                        if real_boxes:
                            gps_str = "unknown"
                            if last_gps["lat"] is not None and last_gps["lon"] is not None:
                                gps_str = f"{last_gps['lat']:.6f},{last_gps['lon']:.6f}"

                            # Salva temporaneo e invia
                            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                                tmp_file.write(jpeg_bytes)
                                temp_path = tmp_file.name

                            def send_and_cleanup():
                                try:
                                    notify_if_danger(real_boxes, gps=gps_str, image_path=temp_path)
                                    time.sleep(0.2)
                                finally:
                                    try:
                                        os.remove(temp_path)
                                    except Exception as e:
                                        print(f"⚠️ Cleanup warning: {e}")

                            threading.Thread(target=send_and_cleanup, daemon=True).start()

                        # Broadcast detection ai web clients (solo se oggetti rilevati)
                        if real_boxes:
                            # Qui puoi inviare direttamente i dati della detection e, se vuoi, anche l'immagine annotata
                            self.broadcast_detection_update(real_boxes, t1 - t0, jpeg_bytes)

                        if detection_count % 10 == 0:
                            print(
                                f"🔍 Detection #{detection_count}: {len(real_boxes)} objects in {(t1 - t0):.3f}s")
                    except Exception as e:
                        print(f"❌ Detection error: {e}")
                else:
                    with detection_lock:
                        latest_detection = None
                    time.sleep(0.05)
            except Exception as e:
                print(f"💥 Detection worker error: {e}")
            time.sleep(0.001)

    def broadcast_detection_update(self, boxes, processing_time, annotated_jpeg=None):
        """
        Broadcast detection results (boxes + optionally annotated image) to web clients.
        - boxes: list of dicts with detection data
        - processing_time: float (seconds)
        - annotated_jpeg: bytes, JPEG-encoded image with boxes/labels (optional but recommended)
        """
        detection_data = {
            'type': 'detection_update',
            'objects_count': int(len(boxes)),
            'boxes': [
                {
                    "x": int(box["x"]),
                    "y": int(box["y"]),
                    "w": int(box["w"]),
                    "h": int(box["h"]),
                    "class_id": int(box.get("class_id", 0)),
                    "confidence": float(box.get("confidence", 0)),
                    "label": box.get("label", "")
                }
                for box in boxes
            ],
            'processing_time': float(processing_time),
            'timestamp': float(time.time())
        }
        if annotated_jpeg is not None:
            detection_data['annotated_frame'] = base64.b64encode(annotated_jpeg).decode("utf-8")

        # Example: Use a queue for thread safety (as discussed in previous messages)
        # Put the detection_data in a queue to be sent by an async consumer
        if not hasattr(self, 'broadcast_queue'):
            from queue import Queue
            self.broadcast_queue = Queue()
        self.broadcast_queue.put(detection_data)


    async def handle_client(self, websocket, path):
        """Gestisce connessioni WebSocket"""
        client_ip = websocket.remote_address[0]
        print(f"🔌 New WebSocket connection from {client_ip}")

        try:
            # Aspetta messaggio di identificazione
            hello_msg = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            hello_data = json.loads(hello_msg)

            if hello_data.get('type') == 'esp32_hello':
                await self.handle_esp32_connection(websocket, client_ip, hello_data)
            else:
                await self.handle_web_connection(websocket, client_ip, hello_data)

        except asyncio.TimeoutError:
            print(f"⏰ Client {client_ip} identification timeout")
        except websockets.exceptions.ConnectionClosed:
            print(f"❌ Client {client_ip} disconnected during handshake")
        except Exception as e:
            print(f"❌ Error handling client {client_ip}: {e}")
        finally:
            await self.cleanup_client(websocket)

    async def handle_esp32_connection(self, websocket, client_ip, hello_data):
        """Gestisce connessione ESP32-CAM"""
        connected_clients['esp32'] = {
            'websocket': websocket,
            'ip': client_ip,
            'connected_at': time.time(),
            'frames_received': 0,
            'device_info': hello_data
        }

        print(f"📹 ESP32-CAM connected from {client_ip}")

        # Conferma connessione
        await websocket.send(json.dumps({
            'type': 'esp32_hello_ack',
            'status': 'connected',
            'server_time': time.time(),
            'optimizations': {
                'detection_skip_frames': DETECTION_SKIP_FRAMES,
                'max_detection_age': MAX_DETECTION_AGE,
                'features_enabled': ['object_detection', 'image_saving', 'telegram_notifications', 'gps_tracking']
            }
        }))

        # Notifica web clients
        await self.broadcast_to_authenticated_clients({
            'type': 'esp32_status',
            'connected': True,
            'device_info': hello_data
        })

        # Gestisci messaggi ESP32
        await self.handle_esp32_messages(websocket)

    async def handle_web_connection(self, websocket, client_ip, hello_data):
        """Gestisce connessione client web"""
        # Autenticazione semplificata per ora
        session_id = hello_data.get('session_id', f'session_{int(time.time())}')
        username = hello_data.get('username', 'guest')

        connected_clients['web_clients'][websocket] = {
            'ip': client_ip,
            'username': username,
            'session_id': session_id,
            'connected_at': time.time(),
            'authenticated': True  # Semplificato per ora
        }

        print(f"🌐 Web client connected: {username} from {client_ip}")

        # Invia stato corrente
        await websocket.send(json.dumps({
            'type': 'connection_ack',
            'authenticated': True,
            'esp32_status': {
                'connected': connected_clients['esp32'] is not None,
                'device_info': connected_clients['esp32']['device_info'] if connected_clients['esp32'] else None
            },
            'system_status': {
                'negative_effect': negative_effect,
                'object_detection': object_detection,
                'frame_count': frame_count,
                'gps': last_gps,
                'environmental': last_env,
                'detection_count': detection_count
            }
        }))

        # Gestisci messaggi web client
        await self.handle_web_messages(websocket)

    async def handle_esp32_messages(self, websocket):
        """Gestisce messaggi dall'ESP32-CAM"""
        global latest_frame, frame_count, last_gps, last_env

        async for message in websocket:
            try:
                data = json.loads(message)

                if 'frame' in data:
                    # Frame video - OTTIMIZZATO
                    await self.process_video_frame(data)

                elif data.get('type') == 'sensor_data':
                    # Dati sensori
                    await self.process_sensor_data(data)

                elif data.get('type') == 'heartbeat':
                    # Heartbeat ESP32 - risposta rapida
                    await websocket.send(json.dumps({
                        'type': 'heartbeat_ack',
                        'timestamp': time.time()
                    }))

            except json.JSONDecodeError:
                print("❌ Invalid JSON from ESP32")
            except Exception as e:
                print(f"❌ Error processing ESP32 message: {e}")

    async def process_video_frame(self, data):
        """Processa frame video dall'ESP32 - OTTIMIZZATO"""
        global latest_frame, frame_count

        frame_count += 1
        connected_clients['esp32']['frames_received'] = frame_count

        frame_b64 = data['frame']
        frame_size = data.get('size', 0)

        # Decodifica frame
        img_bytes = base64.b64decode(frame_b64)
        latest_frame = img_bytes

        # RIMOZIONE QUEUE HTTP - Non più necessario
        # while not frame_queue.empty(): ...
        # frame_queue.put(img_bytes)

        # Queue per detection solo se attivo
        if object_detection:
            while not detection_frame_queue.empty():
                try:
                    detection_frame_queue.get_nowait()
                except:
                    break
            try:
                detection_frame_queue.put_nowait(img_bytes)
            except:
                pass

        # Applica effetti OTTIMIZZATO
        processed_frame = self.apply_current_effects_to_image(img_bytes)
        processed_b64 = base64.b64encode(processed_frame).decode('utf-8')

        # Broadcast immediato ai web clients
        await self.broadcast_to_authenticated_clients({
            'type': 'video_frame',
            'frame': processed_b64,
            'size': len(processed_frame),
            'frame_number': frame_count,
            'timestamp': time.time(),
            'effects_applied': {
                'negative': negative_effect,
                'detection': object_detection
            }
        })

        # Log ridotto
        if frame_count % 100 == 0:
            print(f"📹 Frame #{frame_count}: {frame_size} bytes -> processed and broadcasted")

    async def process_sensor_data(self, data):
        """Processa dati sensori"""
        global last_gps, last_env

        if 'gps' in data:
            last_gps.update(data['gps'])
        if 'environmental' in data:
            last_env.update(data['environmental'])

        # Broadcast ai web clients
        await self.broadcast_to_authenticated_clients({
            'type': 'sensor_update',
            'gps': last_gps,
            'environmental': last_env,
            'timestamp': time.time()
        })

    def apply_current_effects_to_image(self, img_data):
        """Applica effetti correnti all'immagine - OTTIMIZZATO"""
        try:
            img_array = np.frombuffer(img_data, np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if img is None:
                return img_data

            detection_applied = False

            # Object detection overlay - OTTIMIZZATO per fluidità
            if object_detection and latest_detection:
                with detection_lock:
                    current_time = time.time()
                    if (latest_detection and
                            current_time - latest_detection['timestamp'] <= MAX_DETECTION_AGE):
                        boxes = latest_detection.get('boxes', [])
                        if boxes:
                            img = self.draw_detection_boxes_on_live_frame(img, boxes)
                            detection_applied = True

            # Negative effect
            if negative_effect:
                img = cv2.bitwise_not(img)

            # Encode risultato con qualità ottimizzata
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, 90]  # Qualità leggermente ridotta per performance
            ret, buffer = cv2.imencode('.jpg', img, encode_params)
            if ret:
                return buffer.tobytes()
            else:
                return img_data

        except Exception as e:
            print(f"❌ Error applying effects: {e}")
            return img_data

    def draw_detection_boxes_on_live_frame(self, live_img, boxes_data):
        """Disegna box di detection sull'immagine - OTTIMIZZATO"""
        global red_classes_config
        red_classes_config = db.get_dangerous_classes()
        overlay_img = live_img.copy()
        for box in boxes_data:
            x, y, w, h = box['x'], box['y'], box['w'], box['h']
            label = box['label']
            confidence = box['confidence']
            color = (0, 0, 255) if label in red_classes_config else (0, 255, 0)

            # Box più spesso per visibilità
            cv2.rectangle(overlay_img, (x, y), (x + w, y + h), color, 3)

            # Label ottimizzato
            label_text = f"{label} {confidence:.1f}"  # 1 decimale invece di 2
            font_scale = 0.6  # Font leggermente più piccolo
            text_thickness = 2
            (label_w, label_h), baseline = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale,
                                                           text_thickness)

            # Posizionamento label centrato
            center_x = x + w // 2
            text_x = center_x - label_w // 2
            text_y = y - 10
            if text_y - label_h < 0:
                text_y = y + h + label_h + 10

            # Background label più sottile
            padding = 4
            cv2.rectangle(overlay_img,
                          (text_x - padding, text_y - label_h - padding),
                          (text_x + label_w + padding, text_y + padding),
                          color, -1)
            cv2.putText(overlay_img, label_text, (text_x, text_y),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), text_thickness)
        return overlay_img

    async def handle_web_messages(self, websocket):
        """Gestisce messaggi dai web clients"""
        global current_command, negative_effect, object_detection

        async for message in websocket:
            try:
                data = json.loads(message)
                client_info = connected_clients['web_clients'].get(websocket, {})
                username = client_info.get('username', 'unknown')

                if data.get('type') == 'command':
                    # Comando di controllo
                    command = data.get('command', '')
                    current_command = command

                    print(f"🎮 Command from {username}: {command}")

                    # Invia all'ESP32 se connesso
                    if connected_clients['esp32']:
                        await connected_clients['esp32']['websocket'].send(json.dumps({
                            'type': 'control_command',
                            'command': command,
                            'timestamp': time.time()
                        }))

                    # Conferma a tutti i web clients
                    await self.broadcast_to_authenticated_clients({
                        'type': 'command_ack',
                        'command': command,
                        'username': username,
                        'timestamp': time.time()
                    })

                elif data.get('type') == 'toggle_effect':
                    # Toggle effetti video
                    effect_type = data.get('effect')

                    if effect_type == 'negative':
                        negative_effect = not negative_effect
                        print(f"🎨 Negative effect: {'ON' if negative_effect else 'OFF'} by {username}")

                        await self.broadcast_to_authenticated_clients({
                            'type': 'effect_toggled',
                            'effect': 'negative',
                            'enabled': negative_effect,
                            'username': username
                        })

                    elif effect_type == 'detection':
                        object_detection = not object_detection
                        if not object_detection:
                            with detection_lock:
                                latest_detection = None

                        print(f"🔍 Object detection: {'ON' if object_detection else 'OFF'} by {username}")

                        await self.broadcast_to_authenticated_clients({
                            'type': 'effect_toggled',
                            'effect': 'detection',
                            'enabled': object_detection,
                            'username': username
                        })

                elif data.get('type') == 'save_image':
                    # Salvataggio immagine
                    await self.handle_save_image(websocket, username)

            except json.JSONDecodeError:
                print(f"❌ Invalid JSON from web client {username}")
            except Exception as e:
                print(f"❌ Error processing web message from {username}: {e}")

    async def handle_save_image(self, websocket, username):
        """Gestisce salvataggio immagine"""
        global latest_frame

        if latest_frame is None:
            await websocket.send(json.dumps({
                'type': 'save_error',
                'error': 'No frame available to save'
            }))
            return

        try:
            # Applica effetti correnti
            processed_frame = self.apply_current_effects_to_image(latest_frame)

            # Prepara metadati
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            filename = f"captured_{timestamp}.jpg"

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
                'saved_by': username
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

            # Salva in GridFS
            image_id = db.save_image_metadata(processed_frame, image_record)
            image_record['mongodb_id'] = image_id

            print(f"📸 Image saved by {username}: {filename}")

            # Conferma salvataggio
            effects_info = []
            if negative_effect:
                effects_info.append("negative")
            if object_detection and detection_objects_count > 0:
                effects_info.append(f"detection({detection_objects_count} objects)")
            elif object_detection:
                effects_info.append("detection(no objects)")

            await websocket.send(json.dumps({
                'type': 'save_success',
                'image': {
                    'filename': filename,
                    'size': len(processed_frame),
                    'effects_applied': effects_info,
                    'mongodb_id': image_id
                },
                'database': 'mongodb_gridfs'
            }))

            # Notifica altri client
            await self.broadcast_to_authenticated_clients({
                'type': 'image_saved',
                'filename': filename,
                'saved_by': username,
                'timestamp': time.time()
            }, exclude=websocket)

        except Exception as e:
            print(f"❌ Error saving image: {e}")
            await websocket.send(json.dumps({
                'type': 'save_error',
                'error': f"Failed to save image: {str(e)}"
            }))

    async def broadcast_to_authenticated_clients(self, message, exclude=None):
        """Invia messaggio a tutti i web clients autenticati"""
        if not connected_clients['web_clients']:
            return

        tasks = []
        for websocket, client_info in connected_clients['web_clients'].items():
            if exclude and websocket == exclude:
                continue
            if client_info.get('authenticated', False):
                tasks.append(self.send_to_client(websocket, message))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def send_to_client(self, websocket, message):
        """Invia messaggio a singolo client"""
        try:
            await websocket.send(json.dumps(message))
        except websockets.exceptions.ConnectionClosed:
            # Cleanup automatico
            if websocket in connected_clients['web_clients']:
                del connected_clients['web_clients'][websocket]
        except Exception as e:
            print(f"❌ Error sending to client: {e}")

    async def cleanup_client(self, websocket):
        """Cleanup connessione client"""
        # ESP32 cleanup
        if connected_clients['esp32'] and connected_clients['esp32']['websocket'] == websocket:
            connected_clients['esp32'] = None
            print("📹 ESP32-CAM disconnected")
            await self.broadcast_to_authenticated_clients({
                'type': 'esp32_status',
                'connected': False
            })

        # Web client cleanup
        if websocket in connected_clients['web_clients']:
            client_info = connected_clients['web_clients'][websocket]
            username = client_info.get('username', 'unknown')
            del connected_clients['web_clients'][websocket]
            print(f"🌐 Web client disconnected: {username}")

    def start_server(self):
        """Avvia server WebSocket"""
        print(f"🚀 Starting OPTIMIZED IoT WebSocket server on {self.host}:{self.websocket_port}")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        start_server = websockets.serve(
            self.handle_client,
            self.host,
            self.websocket_port,
            max_size=2 ** 20,  # 1MB max message size
            ping_interval=20,
            ping_timeout=10
        )

        #loop = asyncio.get_event_loop()
        loop.run_until_complete(start_server)

        print(f"✅ OPTIMIZED IoT WebSocket server running on ws://{self.host}:{self.websocket_port}")
        print("🔍 Object detection: OPTIMIZED with frame skipping and faster processing")
        print("📸 Image saving: GridFS storage")
        print("🤖 Telegram: Automatic notifications")
        print("📊 All IoT features: Integrated and optimized")

        loop.run_forever()


# ===========================
# HTTP SERVER MINIMALE (SOLO PER COMANDI FALLBACK E GALLERY)
# ===========================

from flask import Flask, Response, request, render_template, jsonify, send_from_directory
from flask import session, redirect, url_for, flash, render_template

app = Flask(__name__)
app.secret_key = generate_secret_key()


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
@login_required
def logout():
    session.clear()
    flash('Logout effettuato con successo!', 'info')
    return redirect(url_for('login'))


server = IoTWebSocketServer(host='0.0.0.0', websocket_port=8765, http_port=5000)

@app.route('/')
@login_required
def index():
    return render_template('index.html', websocket_port=server.websocket_port, username=session.get('username'))


@app.route('/gallery')
@login_required
def gallery():
    """Gallery per visualizzare immagini salvate"""
    try:
        # Ottieni immagini da MongoDB
        images_result = db.get_images_paginated(limit=50)
        return render_template('gallery.html',
                               images=images_result['images'],
                               statistics=images_result['statistics'])
    except Exception as e:
        print(f"❌ Gallery error: {e}")
        return f"Gallery error: {str(e)}", 500


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


@app.route('/api/images')
@login_required
def api_images():
    """API per ottenere lista immagini"""
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    try:
        result = db.get_images_paginated(page=page, limit=limit)
        return jsonify(result)
    except Exception as e:
        return jsonify(error=str(e)), 500


@app.route('/saved_images/<filename>')
@login_required
def serve_saved_image(filename):
    """Serve immagini da GridFS"""
    try:
        image_doc = db.images.find_one({"filename": filename})
        if not image_doc:
            return "Image not found", 404

        gridfs_image_id = str(image_doc["gridfs_image_id"])
        image_data, metadata = db.get_image_from_gridfs(gridfs_image_id)

        return Response(
            image_data,
            mimetype=metadata.get('content_type', 'image/jpeg'),
            headers={
                'Content-Disposition': f'inline; filename="{metadata["filename"]}"',
                'Cache-Control': 'public, max-age=3600'
            }
        )
    except Exception as e:
        print(f"❌ Error serving image: {e}")
        return "Error loading image", 500


@app.route('/thumbnails/<filename>')
@login_required
def serve_thumbnail(filename):
    """Serve thumbnails da GridFS"""
    try:
        original_filename = filename.replace("thumb_", "") if filename.startswith("thumb_") else filename
        image_doc = db.images.find_one({"filename": original_filename})
        if not image_doc:
            return "Thumbnail not found", 404

        gridfs_thumbnail_id = str(image_doc["gridfs_thumbnail_id"])
        thumbnail_data, metadata = db.get_thumbnail_from_gridfs(gridfs_thumbnail_id)

        return Response(
            thumbnail_data,
            mimetype=metadata.get('content_type', 'image/jpeg'),
            headers={
                'Cache-Control': 'public, max-age=3600'
            }
        )
    except Exception as e:
        print(f"❌ Error serving thumbnail: {e}")
        return "Error loading thumbnail", 500


@app.route('/control', methods=['POST'])
@login_required
def control():
    """HTTP fallback per comandi di emergenza"""
    global current_command
    direction = request.form.get('direction')
    current_command = direction

    print(f"🎮 HTTP Emergency Command: {direction}")

    # Prova a inviare via WebSocket se ESP32 connesso
    if connected_clients['esp32']:
        try:
            # Questo è un hack per HTTP->WebSocket, normalmente evitare
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                connected_clients['esp32']['websocket'].send(json.dumps({
                    'type': 'control_command',
                    'command': direction,
                    'timestamp': time.time(),
                    'source': 'http_fallback'
                }))
            )
            loop.close()
        except Exception as e:
            print(f"❌ Error sending HTTP command via WebSocket: {e}")

    return jsonify(status="emergency command received", direction=direction)


@app.route('/set_speed', methods=['POST'])
@login_required
def set_speed():
    global current_speed
    try:
        speed = int(request.form.get('speed'))
        if 80 <= speed <= 255:
            current_speed = speed
            return jsonify(status="ok", speed=speed)
        else:
            return jsonify(error="Invalid speed"), 400
    except:
        return jsonify(error="Invalid speed value"), 400


@app.route('/get_command')
@login_required
def get_command():
    """HTTP fallback per ESP32 in caso di problemi WebSocket"""
    return f"{current_command}:speed:{current_speed}"


@app.route('/api/status')
@login_required
def api_status():
    return jsonify({
        'esp32_connected': connected_clients['esp32'] is not None,
        'web_clients_count': len(connected_clients['web_clients']),
        'frame_count': frame_count,
        'effects': {
            'negative': negative_effect,
            'detection': object_detection
        },
        'gps': last_gps,
        'environmental': last_env,
        'detection_stats': {
            'count': detection_count,
            'latest': latest_detection is not None
        },
        'optimizations': {
            'detection_skip_frames': DETECTION_SKIP_FRAMES,
            'max_detection_age': MAX_DETECTION_AGE
        },
        'timestamp': time.time()
    })

@app.route('/api/images/<image_id>', methods=['PUT'])
@login_required
def update_image_metadata(image_id):
    data = request.json
    updates = {}
    if 'tags' in data:
        updates['tags'] = data['tags']
    if 'description' in data:
        updates['description'] = data['description']
    if 'category' in data:
        updates['category'] = data['category']
    # ... altri metadati ...
    db.update_image_metadata(image_id, updates)
    return jsonify({'success': True})


@app.route('/api/images/<image_id>/classify', methods=['POST'])
@login_required
def classify_saved_image(image_id):
    """
    Esegue object detection su un'immagine già salvata, aggiorna i metadati,
    salva una nuova copia con i rettangoli e invia notifica Telegram se necessario.
    """
    try:
        # Trova immagine
        images_result = db.get_images_paginated(limit=1000)
        image = None
        for img in images_result['images']:
            if str(img['id']) == str(image_id):
                image = img
                break
        if not image:
            return jsonify(error="Image not found"), 404

        gridfs_image_id = image['gridfs_image_id']
        image_data, metadata = db.get_image_from_gridfs(gridfs_image_id)

        # Decodifica immagine e applica detection
        img_array = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img is None:
            return jsonify(error="Invalid image data"), 500

        detected_img, detection_data = detect_objects_with_boxes(img)

        # Serializza i bounding box (NO numpy types)
        def to_serializable(box):
            return {
                'x': int(box['x']),
                'y': int(box['y']),
                'w': int(box['w']),
                'h': int(box['h']),
                'label': str(box['label']),
                'confidence': float(box['confidence']),
                'class_id': int(box['class_id'])
            }
        detection_data_serializable = [to_serializable(box) for box in detection_data]

        # Salva la nuova immagine processata su GridFS
        ret, processed_jpg = cv2.imencode('.jpg', detected_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not ret:
            return jsonify(error="Error encoding processed image"), 500

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        filename = f"classified_{timestamp}.jpg"
        gps_str = image.get('gps', 'unknown')

        image_record = {
            'filename': filename,
            'size': len(processed_jpg),
            'created': datetime.now().isoformat(),
            'gps': gps_str,
            'gps_lat': image.get('gps_lat'),
            'gps_lon': image.get('gps_lon'),
            'temperature': image.get('temperature'),
            'humidity': image.get('humidity'),
            'tags': image.get('tags', []),
            'description': image.get('description', ''),
            'analysis': None,
            'detection_active': True,
            'negative_effect': image.get('negative_effect', False),
            'effects_applied': {
                'negative': image.get('negative_effect', False),
                'object_detection': True
            },
            'saved_by': session.get('username'),
            'detection_results': {
                'boxes': detection_data_serializable,
                'objects_count': len(detection_data_serializable),
                'detection_time': float(time.time()),
                'processing_time': 0
            }
        }

        processed_jpg_bytes = processed_jpg.tobytes()
        if int(image_record['detection_results']['objects_count']) > 0:
            image_id_new = db.save_image_metadata(processed_jpg_bytes, image_record)

        # Notifica telegram se "person" trovata
        dangerous = [b for b in detection_data_serializable if b['label'] == "person"]
        if dangerous:
            # Salva su disco temporaneo, invia notifica e cancella
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                tmp_file.write(processed_jpg_bytes)
                temp_path = tmp_file.name
            caption = f"Immagine classificata dalla gallery da {session.get('username')}\n" \
                      f"Oggetti: {', '.join([b['label'] for b in detection_data_serializable])}"
            threading.Thread(
                target=lambda: (notify_if_danger(detection_data_serializable, gps_str, temp_path, caption=caption), os.remove(temp_path)),
                daemon=True
            ).start()

        return jsonify(
            success=True,
            objects_count=len(detection_data_serializable),
            detection=detection_data_serializable,
            new_image_id=image_id_new,
            new_filename=filename
        )
    except Exception as e:
        print(f"❌ Error in classify_saved_image: {e}")
        return jsonify(error=str(e)), 500


@app.route('/api/images/<image_id>/telegram', methods=['POST'])
@login_required
def send_image_via_telegram(image_id):
    """
    Invia l'immagine salvata su Telegram a tutti i chat_id registrati.
    """
    try:
        # Recupera immagine dal DB
        images_result = db.get_images_paginated(limit=1000)
        image = None
        for img in images_result['images']:
            if str(img['id']) == str(image_id):
                image = img
                break
        if not image:
            return jsonify(error="Image not found"), 404

        gridfs_image_id = image['gridfs_image_id']
        image_data, metadata = db.get_image_from_gridfs(gridfs_image_id)

        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
            tmp_file.write(image_data)
            temp_path = tmp_file.name

        label_info = ""
        if image.get('detection_results'):
            detected = image['detection_results']
            label_info = f"\nOggetti: {', '.join([b['label'] for b in detected['boxes']])}"
        gps_str = image.get('gps', 'unknown')
        caption = f"Immagine dalla gallery GridFS (inviata da {session.get('username')}).{label_info}"

        # Importa la funzione del bot già pronta
        from telegram_bot import notify_if_danger
        def send_and_cleanup():
            try:
                notify_if_danger([], gps_str, temp_path, caption=caption)
            finally:
                os.remove(temp_path)
        threading.Thread(target=send_and_cleanup, daemon=True).start()

        return jsonify(success=True, status="sent", storage="GridFS")
    except Exception as e:
        print(f"❌ Error in send_image_via_telegram: {e}")
        return jsonify(error=str(e)), 500

@app.route('/api/yolo_labels')
@login_required
def get_yolo_labels():
    with open(os.path.join('static', 'coco.names')) as f:
        labels = [line.strip() for line in f.readlines() if line.strip()]
    return jsonify({'labels': labels})

@app.route('/api/notification_classes', methods=['GET'])
@login_required
def get_notification_classes():
    return jsonify({'dangerous_classes': db.get_dangerous_classes()})

@app.route('/api/notification_classes', methods=['POST'])
@login_required
def set_notification_classes():
    data = request.get_json()
    dangerous_classes = data.get('dangerous_classes', [])
    db.set_dangerous_classes(dangerous_classes)
    global red_classes_config
    red_classes_config = db.get_dangerous_classes()
    return jsonify({'success': True, 'dangerous_classes': dangerous_classes})

# ---- TELEGRAM API ----
@app.route('/api/telegram/register', methods=['POST'])
@login_required
def telegram_register():
    chat_id = request.json.get('chat_id')
    if not chat_id:
        return jsonify({'error': 'No chat_id'}), 400
    register_chat_id(chat_id)
    return jsonify({'success': True})

@app.route('/api/telegram/test', methods=['POST'])
@login_required
def telegram_test():
    send_to_all_chats("Test notification from IoT system (test API)!")
    return jsonify({'success': True})


def start_http_server():
    """Avvia server HTTP minimale"""
    app.run(host='0.0.0.0', port=server.http_port, debug=False, threaded=True)

def start_ws_server():
    server = IoTWebSocketServer(host='0.0.0.0', websocket_port=8765, http_port=5000)
    server.start_server()


if __name__ == "__main__":
    # Avvia WebSocket in background
    ws_thread = threading.Thread(target=start_ws_server, daemon=True)
    ws_thread.start()

    # Avvia Flask HTTP SERVER nel thread principale!
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

