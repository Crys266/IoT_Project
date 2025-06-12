# IoT_Project
# 🛻 Radio-Controlled Car for Surveillance and Data Retrieval

## 📌 Project Overview

This IoT project is centered around an RC (Radio-Controlled) Car equipped with sensors and smart features, designed for:

- **Surveillance**: Monitoring hard-to-reach or sensitive areas using real-time video.
- **Data Retrieval**: Collecting environmental data such as temperature, humidity, or gas levels, or mapping terrain in exploration contexts.

The RC Car can be remotely operated over the Internet through a **dedicated WebApp**. The system includes a camera for live video feed, various onboard sensors, and the ability to process and respond to image data through server-side machine learning.

The WebApp (hosted on a Python server) enables users to:
- View the car’s perspective via a real-time video stream.
- Control the car's movement (steering, speed, direction).
- Manage sensors and peripherals (e.g., LEDs, distance sensors).
- Save image frames for further analysis.
- Run object recognition on saved images.
- Receive automated alerts through a Telegram bot when specific objects are detected.

---

## ✅ Functional Requirements

| ID   | Title                         | Description                                                                                     | Input                                           | Output                                       |
|------|-------------------------------|-------------------------------------------------------------------------------------------------|------------------------------------------------|----------------------------------------------|
| FR1  | Remote Vehicle Control        | Remotely control the RC Car via the WebApp (steering, speed, direction).                       | User commands from WebApp                      | RC Car movement                              |
| FR2  | Real-time Image Retrieval     | Display real-time video from the onboard camera in the WebApp.                                 | Camera video stream                            | Real-time video stream in WebApp             |
| FR3  | Sensor Management             | Monitor environmental/operational data via onboard sensors.                                     | Sensor data                                    | Sensor readings on WebApp                    |
| FR4  | Image Data Archiving          | Save specific image frames from the video stream.                                               | User command to capture frame                  | Image frame saved                            |
| FR5  | Object Recognition            | Detect and classify objects using a machine learning model.                                     | Saved image frames                             | Recognized objects and labels                |
| FR6  | Automated Notifications       | Notify Telegram bot subscribers when specific objects are detected.                             | Detected object labels                         | Telegram message with alert                  |
| FR7  | Vehicle Geolocation Tracking  | Show the current location of the RC Car on the WebApp map.                                      | GPS coordinates                                | Location displayed on map interface          |

---

## 📋 Non-Functional Requirements

| ID   | Title                | Description                                                                                   |
|------|----------------------|-----------------------------------------------------------------------------------------------|
| NFR1 | System Responsiveness | The WebApp must respond to user inputs within an acceptable delay.                           |
| NFR2 | Battery Efficiency   | The RC Car should operate for at least 1 hour on a full charge under normal conditions.       |
| NFR3 | Scalability          | The system should support adding new sensors and features without significant slowdowns.      |
| NFR4 | Durability           | The RC Car must handle outdoor conditions, including small impacts and vibrations.            |
| NFR5 | Ease of Use          | The WebApp interface must be intuitive for users without technical experience.                |
| NFR6 | Cost-Effectiveness   | The solution must remain affordable to reach a broad range of potential users.                |

---

## 🚀 Technologies Used

- Python (Flask or FastAPI for WebApp backend)
- HTML/CSS/JS (WebApp frontend)
- OpenCV / TensorFlow / PyTorch (for object recognition)
- Telegram Bot API (for alerts)
- Raspberry Pi / ESP32 (microcontroller unit)
- Sensors: Camera, GPS, Ultrasonic, etc.

---

## 📦 Future Improvements

- Add obstacle avoidance
- Integrate SLAM for autonomous navigation
- Expand sensor suite for richer data collection
- Real-time cloud storage and analytics dashboard

---

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## 🤝 Contributions

Pull requests are welcome! Feel free to open issues or suggest new features.

---

## 📬 Contact

For questions or collaborations: [YourEmail@example.com]

