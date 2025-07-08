# IoT_Project

# 🛻 Radio-Controlled Car for Surveillance and Data Retrieval

## 📌 Project Overview

This project implements a radio-controlled (RC) car for surveillance and data retrieval in challenging environments, integrating live video, environmental sensors, object detection, GPS, and a user-friendly web dashboard. The current architecture emphasizes real-time performance, efficient data storage, seamless notifications, and extensibility for future upgrades.

---

## ❗️ Architectural Update (2025)

**This README reflects the latest system architecture. Files with `http_old` in the name are deprecated and no longer used — do not reference or use them. The system now uses:**

- WebSocket-based communication for real-time, low-latency video and control
- MongoDB + GridFS for robust, scalable image and metadata storage
- Telegram Bot for instant notifications of detected objects/events
- Modern, modular codebase ready for new features and sensors

---

## ✅ Functional Requirements

| ID   | Title                      | Description                                                            |
|------|----------------------------|------------------------------------------------------------------------|
| FR1  | Remote Vehicle Control     | Drive the RC Car remotely in real-time                                 |
| FR2  | Real-time Video Streaming  | Live camera stream with low latency                                    |
| FR3  | Sensor Management          | Collect and visualize environmental & operational data                 |
| FR4  | Image Frame Saving         | Save specific frames for later analysis                                |
| FR5  | Automatic Object Detection | YOLOv3 object recognition on demand or automatically                   |
| FR6  | Telegram Notifications     | Instant alerts for specified detected objects                          |
| FR7  | GPS Position Tracking      | Real-time location displayed in the web dashboard                      |

---

## 🏗️ System Architecture

```
    +------------------+       WebSocket      +-----------------------+      HTTP/WebSocket        +------------------------+
    |   ESP32-CAM      | <------------------> |  Flask WebSocket/HTTP | <-----------------------> |    Web Dashboard UI    |
    +------------------+                      |   (app_ws.py)         |                          +------------------------+
         |   |   |                            +-----------------------+      REST API
         |   |   |                                      |
         |   |   +-- UART/Serial <----> NodeMCU (GPS, DHT11, etc.)
         |
         +--- DC Motors (PWM), Camera, Sensors
```

- **Video and sensor data** is streamed from the ESP32-CAM to Flask via WebSocket for near real-time processing and visualization.
- **Object detection** runs in a dedicated thread for speed, notifying the user via Telegram only for relevant events (e.g., "person" detected).
- **Images and metadata** are saved to MongoDB/GridFS, including thumbnails and environmental data.
- **Web dashboard** provides real-time control, gallery, and sensor views, all via WebSocket/REST API.

---

## 📁 Project Structure

```
IoT_Project/
├── WebApp/
│   ├── app_ws.py              # Main Flask + WebSocket backend (use this)
│   ├── object_detection.py    # YOLOv3 detection logic
│   ├── database.py            # MongoDB/GridFS storage
│   ├── telegram_bot.py        # Telegram Bot integration
│   ├── auth.py                # User authentication system
│   ├── static/
│   │   ├── yolov3.weights     # YOLOv3 weights
│   │   ├── yolov3.cfg         # YOLOv3 config
│   │   ├── coco.names         # COCO labels
│   │   └── styles.css         # Web dashboard CSS
│   └── templates/
│       ├── index_ws.html      # Web dashboard UI (WebSocket-based)
│       └── login.html         # Login interface
├── esp32_cam/
│   ├── main.ino               # ESP32-CAM firmware (send frames, receive commands via WS)
│   └── camera_pins.h          # Camera pinout for AI Thinker
├── NodeMCU/
│   └── NodeMCU.ino            # Environmental sensors & GPS, serial to ESP32-CAM
```

**❌ Files with `*_http_old*` are obsolete and NOT used in the current version.**

---

## 🌐 Requirements

### Backend
- Python 3.x
- Flask
- websockets
- OpenCV (`opencv-python`)
- NumPy
- pymongo + gridfs
- bcrypt (for authentication)

Install dependencies:
```bash
pip install flask websockets opencv-python numpy pymongo gridfs bcrypt
```

### Firmware
- ESP32-CAM (AI Thinker)
- Arduino IDE + ESP32 Board Manager
- Libraries: `esp_camera`, `WiFi.h`, `WebSocketsClient.h` (for WebSocket support), `HTTPClient.h` (optional for fallback)
- NodeMCU for sensor bridge (TinyGPSPlus, DHT)

---

## ▶️ Running the System

1. **Start the WebSocket/HTTP server:**
   ```bash
   cd WebApp
   python app_ws.py
   ```
   Access the dashboard at: [http://localhost:5000](http://localhost:5000)

2. **Flash the ESP32-CAM firmware:**
   - Use `main.ino` in `esp32_cam/`, set your WiFi credentials.
   - Ensure WebSocket connection is enabled in the firmware.

3. **(Optional) Flash NodeMCU:**
   - Use `NodeMCU.ino` to bridge GPS/DHT11 data via UART to ESP32-CAM.

4. **Open the Web Dashboard:**
   - Log in (default: `admin` / `admin123`)
   - Control the car, view live video, and manage images.

---

## ⚡ Key Features & Improvements

- **WebSocket-based streaming**: Ultra-low latency, robust against network glitches.
- **Efficient video processing**: Object detection runs in background, skips frames for performance, and only notifies on important detections.
- **GridFS image storage**: Scalable, no filename collisions, fast thumbnails, and metadata search.
- **Modular expansion**: Easily add new sensors, control modes, or AI features.
- **User authentication**: Secure login, credential update, and session management.
- **Telegram integration**: Real-time alerts, customizable notification rules.
- **Optimized for real-world use**: Non-blocking, robust error handling, performance logging.

---

## 🔄 API Overview

- **WebSocket**:
  - Real-time video frame delivery
  - Command/control messages
  - Sensor and detection event updates
- **HTTP REST (select endpoints):**
  - `/api/images` — paginated saved images (metadata)
  - `/saved_images/<filename>` — serve image from GridFS
  - `/thumbnails/<filename>` — serve thumbnail
  - `/api/images/<id>/classify` — run detection on saved image
  - `/api/images/<id>/telegram` — send image via Telegram

---

## 📌 Notes & Best Practices

- **Do not use or reference `*_http_old*` files**. The new system is faster, more robust, and fully WebSocket-based.
- Make sure MongoDB is running (`localhost:27017` by default).
- Use separate (external) power for motors and ESP32-CAM for stability.
- Always change default admin credentials before deploying in production.
- For best performance, run backend on a machine with sufficient CPU/RAM for OpenCV.

---

## 🚀 Motivation for Architectural Changes

- **Why WebSocket?** HTTP polling caused high latency and server load. WebSocket enables real-time, bidirectional communication, improving video smoothness and command responsiveness.
- **Why GridFS?** Filesystem storage had scaling and concurrency issues. GridFS allows safe concurrent access, easy metadata queries, and robust storage.
- **Why modular backend?** To allow for future expansion (e.g., new ML models, sensor types, or notification channels) with minimal refactoring.

---

## 🛠️ Extending the System

- Add new sensor modules: Update NodeMCU.ino and extend WebApp for new data fields.
- Add new detection rules: Edit `object_detection.py` and `telegram_bot.py`.
- Add user roles or multi-user support: Extend `auth.py` and user management UI.

---

## 📃 Credits & License

Developed by [Crys266](https://github.com/Crys266) and collaborators.

MIT License. See `LICENSE` for details.
