# IoT_Project

## Overview

Radio-controlled car for surveillance and environmental data collection, with real-time video streaming, sensor/GPS data, object detection (YOLOv3), notifications, and a web dashboard.  
All communication is via WebSocket. Images and metadata are saved in MongoDB/GridFS.

---

## System Architecture

```
    +-----------------+           WebSocket           +------------------------------+             HTTP/WebSocket             +----------------------+
    |    ESP32-CAM    | <---------------------------> |        Flask Backend         | <------------------------------------> |   Web Dashboard UI   |
    +-----------------+                               |         (app.py)             |                                     +----------------------+
         |                                             +------------------------------+
         | (UART/Serial)
         v
    +-----------------+
    |    NodeMCU      |  (GPS, DHT11, etc.)
    +-----------------+
```

- ESP32-CAM: Streams JPEG video frames and sensor data via WebSocket; receives movement and effect commands.
- NodeMCU: (optional) Sends GPS and environmental sensor data to ESP32-CAM via UART.
- Flask Backend: Handles all WebSocket and HTTP connections, video relay, image saving, object detection (YOLOv3), MongoDB/GridFS storage, Telegram notifications, user authentication, REST API.
- Web Dashboard: Real-time control, live video, sensor and detection info, gallery, and configuration UI.

---

## Project Structure

```
IoT_Project/
├── docker-compose.yml          # Docker Compose file
├── WebApp/
│   ├── Dockerfile              # Dockerfile for backend
│   ├── requirements.txt        # Python dependencies
│   ├── app.py                  # Main backend (Flask + WebSocket + REST API)
│   ├── object_detection.py     # YOLOv3 detection logic (OpenCV)
│   ├── database.py             # MongoDB/GridFS storage logic
│   ├── telegram_bot.py         # Telegram bot notification system
│   ├── auth.py                 # User authentication
│   ├── static/
│   │   ├── yolov3.weights      # YOLO weights (see requirements below)
│   │   ├── yolov3.cfg          # YOLO config
│   │   ├── coco.names          # Class labels
│   │   └── styles/ js/         # Dashboard CSS/JS
│   └── templates/
│       ├── index_ws.html       # Main dashboard
│       ├── gallery.html        # Image gallery
│       └── login.html          # Login UI
├── ESP32Cam/
│   └── esp32cam_ws.ino         # ESP32-CAM firmware (WebSocket)
├── NodeMCU/
│   └── NodeMCU.ino             # (optional) GPS and sensors firmware
```

---

## Requirements

Python 3.x

Backend dependencies:
You can install all backend python dependencies from the `WebApp/requirements.txt` file:
```bash
pip install -r WebApp/requirements.txt
```

YOLOv3 weights file: 
You must manually download the YOLOv3 weights file, as it is too large to be stored on GitHub.  
Download it with:  
```bash
wget https://data.pjreddie.com/files/yolov3.weights -P WebApp/static/
```
This file is required for object detection to work correctly and must be placed in the `WebApp/static/` directory.

ESP32-CAM firmware:
- Arduino IDE + ESP32 board packages
- Required libraries: esp_camera, WiFi.h, WebSocketsClient.h, ArduinoJson.h, base64.h, WiFiManager.h

NodeMCU firmware (optional):
- Libraries: TinyGPSPlus, DHT11, SoftwareSerial

---

## Docker Support

### Why Docker?

Docker allows you to package the backend and all its dependencies into containers, making setup easier and ensuring the application runs the same way everywhere. With Docker Compose, you can launch both the Flask backend and a MongoDB instance with a single command, without having to manually install Python libraries or MongoDB locally.

### Running with Docker Compose

Make sure you have [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) installed.

1. From the project root directory, build and start the services:
   ```bash
   docker compose up -d --build
   ```

   This will build the Flask backend (using `WebApp/Dockerfile` and `WebApp/requirements.txt`) and start both the backend and MongoDB containers in the background.

2. To stop and remove the containers, run:
   ```bash
   docker compose down
   ```

---

## Setup & Usage

1. **(If not using Docker)** Start MongoDB (default: `localhost:27017`)
2. Start the backend server:
   ```bash
   cd WebApp
   python app.py
   ```
   Dashboard: [http://localhost:5000](http://localhost:5000)
3. Flash ESP32-CAM:
   - Upload `esp32cam_ws.ino` (set your WiFi credentials).
   - On boot, connects to Flask backend via WebSocket.
4. (Optional) Flash NodeMCU:
   - Upload `NodeMCU.ino` to send GPS and sensor data via UART to ESP32-CAM.
5. Login:
   - Default credentials: `admin` / `admin123`
6. Use the dashboard for live video, control, sensors, gallery, and detection.

---

## API

- **WebSocket:**  
  - Video frames, commands, sensor updates, detection events.

- **HTTP Endpoints** (login required):  
  - `/api/images` — list images  
  - `/saved_images/<filename>` — fetch image  
  - `/thumbnails/<filename>` — fetch thumbnail  
  - `/api/images/<id>/classify` — run detection on saved image  
  - `/api/images/<id>/telegram` — send image via Telegram  
  - `/api/yolo_labels` — list detection classes  
  - `/api/notification_classes` — get/set alert classes

---
