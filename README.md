# IoT_Project
# 🛻 Radio-Controlled Car for Surveillance and Data Retrieval

## 🔍 Project Overview

This IoT project involves the development of a Radio-Controlled (RC) Car equipped with sensors and electronic modules, designed for two main applications:

- **Surveillance**: Monitoring hard-to-reach or restricted areas using a live camera stream.
- **Environmental Data Collection**: Measuring parameters such as temperature, humidity, or gas levels, useful for exploration or field analysis.

The RC Car is remotely operated through a **WebApp** connected via **ESP32**, and features:

- Remote control of vehicle motion (steering, speed, direction)
- Real-time video streaming from an onboard camera
- Frame capture and saving functionality
- Image analysis via a server-side machine learning algorithm
- Automatic Telegram notifications when specific objects are detected

An **Arduino board** handles data acquisition from the sensors mounted on a breadboard, allowing for future expansion with additional modules.

---

## ✅ Functional Requirements

| ID   | Title                        | Description                                                                      | Input                                        | Output                                 |
|------|------------------------------|----------------------------------------------------------------------------------|---------------------------------------------|----------------------------------------|
| FR1  | Remote Vehicle Control       | Allows remote control of the RC Car via the WebApp (steering, speed, direction) | User commands from WebApp                   | RC Car movement                         |
| FR2  | Real-time Image Retrieval    | Streams real-time video from the onboard camera to the WebApp                   | Video stream from camera                    | Live video feed in WebApp               |
| FR3  | Sensor Management            | Monitors environmental data from onboard sensors                                | Sensor data (e.g., temperature, gas, etc.)  | Sensor readings displayed in WebApp     |
| FR4  | Image Data Saving            | Allows the operator to save specific video frames                               | User command to save frame                  | Image frame saved                       |
| FR5  | Object Recognition           | Identifies objects in saved images using a machine learning algorithm           | Saved image frames                          | Recognized object labels                |
| FR6  | Automated Notifications      | Sends Telegram alerts based on recognized objects                               | Detected object labels                      | Telegram message sent to subscribers    |
| FR7  | GPS Module Integration       | Displays the current position of the RC Car on the WebApp                       | GPS coordinates from the onboard module     | Car position shown on a map interface   |

---

## 📋 Non-Functional Requirements

| ID   | Title                 | Description                                                                        |
|------|-----------------------|------------------------------------------------------------------------------------|
| NFR1 | System Responsiveness | The WebApp must respond to user inputs with minimal latency                       |
| NFR2 | Battery Efficiency    | The system should operate for at least 1 hour on a fully charged battery          |
| NFR3 | Scalability           | The system must support the addition of new sensors without major performance loss|
| NFR4 | Durability            | The RC Car must withstand outdoor use, including minor shocks and vibrations      |
| NFR5 | Ease of Use           | The WebApp interface should be intuitive for non-technical users                  |
| NFR6 | Affordability         | The system must be cost-effective and realizable with a limited budget            |

---

## 🔧 Main Hardware Components

- **ESP32** – Handles Wi-Fi connectivity and communication with the WebApp  
- **Arduino** – Manages sensor data collection  
- **Camera Module** – Provides live video feed  
- **Sensor Modules** – For temperature, gas, ultrasonic distance, etc.  
- **GPS Module** – For real-time location tracking  
- **Telegram Bot** – For automated user notifications

