# IoT_Project
# 🛻 Radio-Controlled Car for Surveillance and Data Retrieval

## 📌 Project Overview

This project involves the development of a Radio-Controlled (RC) Car designed for surveillance and data retrieval in specific environments. The RC Car is equipped with sensors and control systems to collect useful information in remote or hard-to-reach areas.

### Example Applications:
- **Surveillance**: Using cameras to monitor areas that are difficult to access or require security oversight.
- **Data Retrieval**: Gathering environmental data such as temperature, humidity, or gas concentration, or mapping terrain in exploration scenarios.

To fulfill these goals, the RC Car includes a camera for real-time image acquisition, enabling remote operation over a network connection. The control interface allows the user to:

- Steer the vehicle
- Adjust speed and direction
- Toggle lights
- Manage onboard sensors

Additional functionalities include capturing image frames, analyzing them using object recognition techniques, and sending notifications based on detected objects. The system can also automate alerts when specific labels (e.g., dangerous objects) are identified.

---

## ✅ Functional Requirements

| ID   | Title                      | Requirement Description                                                                 | Input                                | Output                                   |
|------|----------------------------|------------------------------------------------------------------------------------------|--------------------------------------|------------------------------------------|
| FR1  | Remote Vehicle Control     | The system enables an operator to drive the RC Car remotely through the control interface.| User commands (steering, speed, direction) | RC Car movement                          |
| FR2  | Real-time Image Retrieval  | The system retrieves real-time image data using the camera and displays it on the interface.| Camera stream from the RC Car         | Real-time video stream on the interface |
| FR3  | Sensor Management          | The system allows monitoring of environmental and operational parameters via onboard sensors. Sensor readings are collected at a high sampling rate and periodically transmitted to the remote system for visualization.| Sensor data                          | Sensor readings displayed on the interface |
| FR4  | Data Saving                | The operator can save specific image frames for further analysis.                         | User command to save an image         | Image frame saved                        |
| FR5  | Object Recognition         | The system analyzes saved images using a machine learning algorithm to identify objects.  | Saved image frames                    | Recognized objects and their labels      |
| FR6  | Automated Notifications    | The system sends notifications to subscribers when specific objects (e.g., dangerous items) are detected.| Object labels identified             | Notifications sent to the user           |
| FR7  | GPS Module Integration     | The RC Car provides its current position.                                                 | Coordinates from the GPS module       | Current location displayed in the interface |

---

## 📋 Non-Functional Requirements

| ID   | Title                 | Description                                                                                   |
|------|-----------------------|-----------------------------------------------------------------------------------------------|
| NFR1 | System Responsiveness | The control interface must respond to user commands within an acceptable waiting time.        |
| NFR2 | Battery Efficiency    | The system should operate for at least 1 hour on a fully charged battery under standard conditions. |
| NFR3 | Scalability           | The system must allow integration of additional sensors and features without significant performance degradation. |
| NFR4 | Durability            | The RC Car must withstand outdoor use, including minor impacts and vibrations.                |
| NFR5 | Ease of Use           | The control interface must be intuitive for operators with no technical expertise.            |
| NFR6 | Affordability         | The device must be cost-effective to attract a wide range of customers.                       |
---

## 🔧 Main Hardware Components

- **ESP32** – Handles Wi-Fi connectivity and communication with the WebApp  
- **Arduino** – Manages sensor data collection  
- **Camera Module** – Provides live video feed  
- **Sensor Modules** – For temperature, gas, ultrasonic distance, etc.  
- **GPS Module** – For real-time location tracking  
- **Telegram Bot** – For automated user notifications


# 🚗 ESP32-CAM Robot Car con Streaming Video e Controllo Remoto via Flask

Questo progetto combina un'applicazione web Flask con un firmware per **ESP32-CAM** che consente:
- streaming video in tempo reale,
- comandi di movimento (avanti, indietro, sinistra, destra),
- effetti visivi e rilevamento oggetti (YOLOv3) lato server.

---

## 🧱 Componenti del Sistema

### 🧠 **Backend Web (Python + Flask)**

- Riceve immagini dalla ESP32-CAM
- Visualizza lo stream video in tempo reale
- Applica effetti:
  - 🔄 Effetto negativo
  - 🔍 Rilevamento oggetti (YOLOv3)
- Riceve comandi di movimento da UI e li espone via API

### 🔧 **Firmware ESP32-CAM (C++)**

- Si connette al WiFi
- Cattura frame JPEG e li invia al server Flask via HTTP POST
- Legge il comando da Flask via HTTP GET
- Controlla due motori DC per movimento (avanti/indietro, sterzata)

---

## 📁 Struttura del Progetto

```
.
├── app.py                    # Server Flask
├── object_detection.py       # YOLOv3 con OpenCV
├── templates/
│   └── index.html            # Interfaccia utente web
├── static/
│   ├── yolov3.weights        # Pesi YOLOv3
│   ├── yolov3.cfg            # Configurazione YOLOv3
│   └── coco.names            # Classi COCO
├── esp32_cam/
│   ├── main.ino              # Firmware Arduino ESP32-CAM
│   └── camera_pins.h         # Pinout AI Thinker
```

---

## 🌐 Requisiti

### Backend Python
- Python 3.x
- Flask
- OpenCV (`opencv-python`)
- NumPy

Installa con:
```bash
pip install flask opencv-python numpy
```

### Firmware ESP32-CAM
- Scheda ESP32-CAM (es. AI Thinker)
- Arduino IDE + ESP32 Board Manager
- Librerie: `esp_camera`, `WiFi.h`, `HTTPClient.h`

---

## ▶️ Esecuzione

### 1. Avvia il server Flask
```bash
python app.py
```
L'interfaccia sarà disponibile su `http://<IP>:5000`

### 2. Flash del firmware su ESP32-CAM
- Inserisci le tue credenziali WiFi in `main.ino`
- Carica il codice via Arduino IDE
- Dopo il boot, l'ESP:
  - invia immagini a `/upload`
  - legge comandi da `/get_command`

---

## 🔄 API Server

| Endpoint                     | Metodo | Descrizione                              |
|-----------------------------|--------|------------------------------------------|
| `/`                         | GET    | UI di controllo e visualizzazione video  |
| `/upload`                   | POST   | Ricezione immagine da ESP32-CAM          |
| `/video_feed`               | GET    | Stream MJPEG                             |
| `/toggle_negative`          | POST   | Attiva/disattiva effetto negativo        |
| `/toggle_object_detection`  | POST   | Attiva/disattiva YOLOv3                  |
| `/control`                  | POST   | Invia comando di movimento (form)        |
| `/get_command`              | GET    | Legge ultimo comando (per ESP)           |

---

## 🔌 Pinout ESP32-CAM (AI Thinker)

### 📷 Fotocamera

Incluso in `camera_pins.h`:
```cpp
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22
```

### 🛞 Motori

```cpp
#define ENA 14
#define ENB 15
#define IN1 13
#define IN2 12
#define IN3 3
#define IN4 1
```

---

## 🧠 Funzioni di Movimento

Nel firmware ESP32:
- `avanti()`: marcia avanti
- `indietro()`: retromarcia
- `sterzaDestra()`: curva a destra
- `sterzaSinistra()`: curva a sinistra

Controllati tramite PWM con `ledcWrite`.

---

## 📸 Loop del Firmware

- Legge comando da Flask
- Esegue la funzione di movimento
- Cattura immagine dalla fotocamera
- La invia via HTTP POST

---

## 📌 Note Finali

- Verifica che IP e porta tra ESP32-CAM e Flask corrispondano.
- Consigliato l'uso di alimentazione esterna per ESP32-CAM + motori.
- Puoi espandere il progetto con WebSocket, salvataggio immagini, riconoscimento avanzato ecc.


