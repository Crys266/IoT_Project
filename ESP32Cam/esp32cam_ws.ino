#include "esp_camera.h"
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <base64.h>
#include <WiFiManager.h>

// WiFi
const char* flask_server = "10.189.14.187";
const int websocket_port = 8765;  // PORTA WEBSOCKET NATIVA

// WebSocket
WebSocketsClient webSocket;
bool wsConnected = false;
unsigned long framesSent = 0;
unsigned long lastFrameTime = 0;
const unsigned long FRAME_INTERVAL = 100; // 10 FPS

// Motor pins 
struct MOTOR_PINS {
  int pinEn;
  int pinIN1;
  int pinIN2;
};

#define NUM_MOTORS 2
MOTOR_PINS motorPins[NUM_MOTORS] = {
  {12, 13, 15},
  {12, 14, 2}
};

#define FLASH_LED_PIN 4
#define RIGHT_MOTOR 0
#define LEFT_MOTOR 1
#define FORWARD 1
#define BACKWARD -1
#define STOP 0

const int PWMFreq = 1000;
const int PWMResolution = 8;

int globalSpeed = 255;

bool motorsActive = false;

unsigned long lastCommandTime = 0;
const unsigned long COMMAND_TIMEOUT = 250; // ms

// Camera pins
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

#define NODEMCU_RX 3  // U0RXD (ESP32-CAM RX) -- collegato a TX NodeMCU
#define NODEMCU_TX 1  // U0TXD (ESP32-CAM TX) -- collegato a RX NodeMCU

void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
  switch(type) {
    case WStype_DISCONNECTED:
      {
        wsConnected = false;
        Serial.println("[WS] Disconnected");
        break;
      }      
    case WStype_CONNECTED:
      {
        wsConnected = true;
        Serial.printf("[WS] Connected to: %s\n", payload);        
        // Invia identificazione ESP32 per server nativo
        DynamicJsonDocument doc(300);
        doc["type"] = "esp32_hello";
        doc["device"] = "ESP32-CAM";
        doc["version"] = "4.0_native";
        doc["ip"] = WiFi.localIP().toString();
        doc["mac"] = WiFi.macAddress();
        doc["timestamp"] = millis();        
        String jsonString;
        serializeJson(doc, jsonString);
        webSocket.sendTXT(jsonString);        
        break;
      }
    case WStype_TEXT:
      {
        Serial.printf("[WS] Received: %s\n", payload);
        DynamicJsonDocument doc(300);
        DeserializationError error = deserializeJson(doc, payload);
        if (error == DeserializationError::Ok) {
          String msgType = doc["type"].as<String>();
          if (msgType == "control_command") {
            String cmd = doc["command"].as<String>();
            Serial.printf("Command: %s\n", cmd.c_str());
            // Gestione comando velocità
            if(cmd.startsWith("speed:")) {
              int spd = cmd.substring(6).toInt();
              if(spd >= 0 && spd <= 255) {
                setMotorSpeed(spd);
                Serial.printf("Speed: %d\n", spd);
              }
            } else {
              executeCommand(cmd);
            }
          }
        }
        break;
      }
    case WStype_ERROR:
      {
        Serial.printf("[WS] Error: %s\n", payload);
        wsConnected = false;
        break;
      }
    default:
      {
        Serial.printf("[WS] Event type: %u\n", type);
        break;
      }
  }
}

void setup() {
  Serial.begin(115200);
  setupMotors();
  setupFlash();
  setupWiFi();
  setupCamera();
  Serial2.begin(9600, SERIAL_8N1, NODEMCU_RX, NODEMCU_TX); 
  setupWebSocket();
  Serial.println("SYSTEM READY - WEBSOCKET");
}

void setupMotors() {
  for (int i = 0; i < NUM_MOTORS; i++) {
    pinMode(motorPins[i].pinIN1, OUTPUT);
    pinMode(motorPins[i].pinIN2, OUTPUT);
    digitalWrite(motorPins[i].pinIN1, LOW);
    digitalWrite(motorPins[i].pinIN2, LOW);
    ledcAttach(motorPins[i].pinEn, PWMFreq, PWMResolution);
    ledcWrite(motorPins[i].pinEn, 0);
  }
  motorsActive = false;
}

void setupFlash() {
  pinMode(FLASH_LED_PIN, OUTPUT);
  digitalWrite(FLASH_LED_PIN, LOW);
}

void setupWiFi() {
  WiFiManager wifiManager;
  if (!wifiManager.autoConnect("ESP32_SETUP")) {
    Serial.println("WiFiManager failed, AP...");;
  }
  Serial.printf("WiFi connected: %s\n", WiFi.localIP().toString().c_str());
}


void setupCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // Configurazione ottimale per WebSocket nativo
  if(psramFound()) {
    config.frame_size = FRAMESIZE_VGA;     // 640x480
    config.jpeg_quality = 10;            
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.grab_mode = CAMERA_GRAB_LATEST;
  } else {
    config.frame_size = FRAMESIZE_HVGA;    // 480x320
    config.jpeg_quality = 12;             
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_DRAM;
    config.grab_mode = CAMERA_GRAB_LATEST;
  }
  if (esp_camera_init(&config) != ESP_OK) {
    Serial.println("Camera fail");
    return;
  }
  sensor_t * s = esp_camera_sensor_get();
  if (s != nullptr) {
    s->set_vflip(s, 1);
    s->set_hmirror(s, 1);
    s->set_brightness(s, 1);
    s->set_contrast(s, 2);
  }
}

void setupWebSocket() {
  Serial.println("Set WebSocket...");
  webSocket.begin(flask_server, websocket_port, "/");
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(5000);
  Serial.printf("WebSocket: ws://%s:%d/\n", flask_server, websocket_port);
}

void loop() {
  webSocket.loop();
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi lost!");
    delay(1000);
    return;
  }
  if (wsConnected) {
    sendVideoFrame();
    sendHeartbeat();
  }
  static unsigned long lastSensorRead = 0;
  if (millis() - lastSensorRead > 2000) {
    lastSensorRead = millis();
    readAndSendSensorData();
  }
  if (motorsActive && (millis() - lastCommandTime > COMMAND_TIMEOUT)) {
    stopMotors();
  }
  static unsigned long lastStatus = 0;
  if (millis() - lastStatus > 15000) {
    Serial.printf("Status: WS=%s | Frames=%d | Heap=%d\n",
                  wsConnected ? "Connected" : "Disconnected",
                  framesSent, ESP.getFreeHeap());
    lastStatus = millis();
  }
  delay(20);
}

void readAndSendSensorData() {
  static char line[64];
  static byte pos = 0;
  while (Serial2.available()) {
    char c = Serial2.read();
    if (c == '\n' || c == '\r') {
      line[pos] = 0;
      // Parsing compatto: cerca le virgole e usa atof()
      float vals[4] = {0, 0, 0, 0};
      int idx = 0;
      char* token = strtok(line, ",");
      while (token && idx < 4) {
        vals[idx++] = atof(token);
        token = strtok(NULL, ",");
      }
      if (idx == 4) {
        StaticJsonDocument<128> doc;
        doc["type"] = "sensor_data";
        doc["gps"]["lat"] = vals[0];
        doc["gps"]["lon"] = vals[1];
        doc["environmental"]["temperature"] = vals[2];
        doc["environmental"]["humidity"] = vals[3];
        String payload;
        serializeJson(doc, payload);
        webSocket.sendTXT(payload);
      }
      pos = 0;
      line[0] = 0;
    } else if (pos < sizeof(line) - 1) {
      line[pos++] = c;
    }
  }
}

void sendVideoFrame() {
  unsigned long now = millis();
  if (now - lastFrameTime < FRAME_INTERVAL) return;
  camera_fb_t * fb = esp_camera_fb_get();
  if (!fb) return;
  if (fb->len > 0 && fb->len < 120000) { // Max 120KB
    String encodedFrame = base64::encode(fb->buf, fb->len);
    if (encodedFrame.length() < 180000) { // Max 180KB JSON
      DynamicJsonDocument doc(encodedFrame.length() + 300);
      doc["frame"] = encodedFrame;
      doc["size"] = fb->len;
      doc["num"] = framesSent;
      doc["timestamp"] = now;
      String jsonString;
      serializeJson(doc, jsonString);
      bool success = webSocket.sendTXT(jsonString);
      if (success) {
        framesSent++;
        lastFrameTime = now;
        if (framesSent % 50 == 0) {
          Serial.printf("Frame #%d: %d bytes -> %d chars JSON\n",
                        framesSent, fb->len, jsonString.length());
        }
      }
    }
  }
  esp_camera_fb_return(fb);
}


void sendHeartbeat() {
  static unsigned long lastHeartbeat = 0;
  unsigned long now = millis();
  if (now - lastHeartbeat > 20000) { // Ogni 20 secondi
    DynamicJsonDocument doc(200);
    doc["type"] = "heartbeat";
    doc["timestamp"] = now;
    doc["frames_sent"] = framesSent;
    doc["free_heap"] = ESP.getFreeHeap();
    doc["wifi_rssi"] = WiFi.RSSI();
    String jsonString;
    serializeJson(doc, jsonString);
    webSocket.sendTXT(jsonString);
    lastHeartbeat = now;
  }
}

void executeCommand(String cmd) {
  lastCommandTime = millis(); 
  if (cmd.startsWith("speed:")) {
    int spd = cmd.substring(6).toInt();
    if (spd >= 80 && spd <= 255) {
      setMotorSpeed(spd);
      Serial.printf("Speed: %d\n", spd);
    }
  }
  else if (cmd == "n") {
    digitalWrite(FLASH_LED_PIN, HIGH);
    Serial.println("Flash ON");
  } 
  else if (cmd == "m") {
    digitalWrite(FLASH_LED_PIN, LOW);
    Serial.println("Flash OFF");
  }
  else if (cmd == "avanti" || cmd == "a") {
    moveForward();
  } 
  else if (cmd == "indietro" || cmd == "i") {
    moveBackward();
  } 
  else if (cmd == "sinistra" || cmd == "s") {
    turnLeft();
  } 
  else if (cmd == "destra" || cmd == "d") {
    turnRight();
  } 
  else if (cmd == "stop") {
    stopMotors();
  }
}

void rotateMotor(int motorNumber, int motorDirection) {
  if (motorDirection == FORWARD) {
    digitalWrite(motorPins[motorNumber].pinIN1, HIGH);
    digitalWrite(motorPins[motorNumber].pinIN2, LOW);
  }
  else if (motorDirection == BACKWARD) {
    digitalWrite(motorPins[motorNumber].pinIN1, LOW);
    digitalWrite(motorPins[motorNumber].pinIN2, HIGH);
  }
  else {
    digitalWrite(motorPins[motorNumber].pinIN1, LOW);
    digitalWrite(motorPins[motorNumber].pinIN2, LOW);
  }
}

void setMotorSpeed(int speed) {
  globalSpeed = speed;
  for (int i = 0; i < NUM_MOTORS; i++) {
    ledcWrite(motorPins[i].pinEn, speed);
  }
}

void moveForward() {
  rotateMotor(RIGHT_MOTOR, FORWARD);
  rotateMotor(LEFT_MOTOR, FORWARD);
  setMotorSpeed(globalSpeed);
  motorsActive = true;
  Serial.println("FORWARD");
}

void moveBackward() {
  rotateMotor(RIGHT_MOTOR, BACKWARD);
  rotateMotor(LEFT_MOTOR, BACKWARD);
  setMotorSpeed(globalSpeed);
  motorsActive = true;
  Serial.println("BACKWARD");
}

void turnLeft() {
  rotateMotor(RIGHT_MOTOR, FORWARD);
  rotateMotor(LEFT_MOTOR, BACKWARD);
  setMotorSpeed(globalSpeed);
  motorsActive = true;
  Serial.println("LEFT");
}

void turnRight() {
  rotateMotor(RIGHT_MOTOR, BACKWARD);
  rotateMotor(LEFT_MOTOR, FORWARD);
  setMotorSpeed(globalSpeed);
  motorsActive = true;
  Serial.println("RIGHT");
}

void stopMotors() {
  rotateMotor(RIGHT_MOTOR, STOP);
  rotateMotor(LEFT_MOTOR, STOP);
  motorsActive = false;
  Serial.println("STOPPED");
}
