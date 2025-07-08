#include "esp_camera.h"
#include <WiFi.h>
#include <vector>

// ===========================
// WiFi Configuration
// ===========================
const char* ssid = "";
const char* password = "";
const char* flask_server = "";
const int flask_port = 5000;

// ===========================
// MOTOR PINS - CONFIGURAZIONE CONDIVISA
// ===========================
struct MOTOR_PINS {
  int pinEn;   // PWM Enable
  int pinIN1;  // Direction 1
  int pinIN2;  // Direction 2
};

std::vector<MOTOR_PINS> motorPins = {
  {12, 13, 15},  // RIGHT_MOTOR (En=12, IN1=13, IN2=15)
  {12, 14, 2},   // LEFT_MOTOR  (En=12, IN3=14, IN4=2)
};

#define FLASH_LED_PIN 4

#define RIGHT_MOTOR 0
#define LEFT_MOTOR 1
#define FORWARD 1
#define BACKWARD -1
#define STOP 0

// PWM Configuration
const int PWMFreq = 1000;
const int PWMResolution = 8;
const int MAX_SPEED = 255;  // SEMPRE VELOCITÀ MASSIMA

// ===========================
// CONTROLLO CONTINUO - LOGICA SEMPLIFICATA
// ===========================
String currentCommand = "";
String lastActiveCommand = "";
unsigned long lastCommandTime = 0;
const unsigned long COMMAND_TIMEOUT = 500;  // MOLTO PIÙ LUNGO: 5 secondi

bool motorsActive = false;
bool systemInitialized = false;  // NUOVO: evita attivazioni durante init

// CAMERA PINS
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

#define NODEMCU_RX 3
#define NODEMCU_TX 1

#include <HardwareSerial.h>
HardwareSerial nodeSerial(1);

float latitude = 0.0, longitude = 0.0, temperature = 0.0, humidity = 0.0;

void setup() {
  Serial.begin(115200);
  Serial.println("=== ESP32-CAM CONTINUOUS CONTROL ===");
  
  // IMPORTANTE: Inizializza tutto PRIMA di attivare il sistema
  systemInitialized = false;
  
  setupMotors();        // Motori in STOP sicuro
  setupFlash();         // Flash OFF sicuro
  setupWiFi();
  setupCamera();
  nodeSerial.begin(9600, SERIAL_8N1, NODEMCU_RX, NODEMCU_TX);

  // STOP FINALE di sicurezza
  hardStop();
  
  // ORA il sistema è pronto
  systemInitialized = true;
  
  Serial.println("=== SYSTEM READY - CONTINUOUS MODE ===");
  Serial.printf("⚡ Max Speed: %d/255 (100%%)\n", MAX_SPEED);
  Serial.printf("⏰ Command Timeout: %dms\n", COMMAND_TIMEOUT);
  Serial.println("🎮 Press and HOLD commands for continuous movement");
}

void setupMotors() {
  Serial.println("🔧 Setting up motors in SAFE mode...");
  
  for (int i = 0; i < motorPins.size(); i++) {
    // Prima configura come OUTPUT e metti LOW
    pinMode(motorPins[i].pinIN1, OUTPUT);
    pinMode(motorPins[i].pinIN2, OUTPUT);
    digitalWrite(motorPins[i].pinIN1, LOW);
    digitalWrite(motorPins[i].pinIN2, LOW);
    
    // Poi configura PWM e metti a 0
    ledcAttach(motorPins[i].pinEn, PWMFreq, PWMResolution);
    ledcWrite(motorPins[i].pinEn, 0);
    
    Serial.printf("Motor %d: SAFE INIT - En=%d, IN1=%d, IN2=%d\n", 
                  i, motorPins[i].pinEn, motorPins[i].pinIN1, motorPins[i].pinIN2);
  }
  
  motorsActive = false;
  currentCommand = "";
  Serial.println("✅ Motors initialized in STOP state");
}

void setupFlash() {
  Serial.println("💡 Setting up flash in SAFE mode...");
  pinMode(FLASH_LED_PIN, OUTPUT);
  digitalWrite(FLASH_LED_PIN, LOW);  // FORZATAMENTE OFF
  Serial.printf("✅ Flash LED (GPIO%d): FORCED OFF\n", FLASH_LED_PIN);
}

void hardStop() {
  Serial.println("🛑 HARD STOP - Complete system reset");
  
  // STOP MOTORI
  for (int i = 0; i < motorPins.size(); i++) {
    digitalWrite(motorPins[i].pinIN1, LOW);
    digitalWrite(motorPins[i].pinIN2, LOW);
    ledcWrite(motorPins[i].pinEn, 0);
  }
  
  // FLASH OFF
  digitalWrite(FLASH_LED_PIN, LOW);
  
  // RESET VARIABILI
  motorsActive = false;
  currentCommand = "";
  lastActiveCommand = "";
  
  Serial.println("✅ HARD STOP completed");
}

void setupWiFi() {
  Serial.println("🌐 Connecting to WiFi...");
  WiFi.begin(ssid, password);
  WiFi.setSleep(false);
  
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    // MANTIENI STOP durante connessione
    hardStop();
  }
  
  Serial.println("\n✅ WiFi connected!");
  Serial.print("📡 IP: ");
  Serial.println(WiFi.localIP());
}

void setupCamera() {
  Serial.println("📷 Setting up camera...");

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

  if(psramFound()) {
      config.frame_size = FRAMESIZE_SVGA;
      config.jpeg_quality = 8;
      config.fb_count = 2;
      config.fb_location = CAMERA_FB_IN_PSRAM;
      config.grab_mode = CAMERA_GRAB_LATEST;
  } else {
      config.frame_size = FRAMESIZE_VGA;
      config.jpeg_quality = 10;
      config.fb_count = 1;
      config.fb_location = CAMERA_FB_IN_DRAM;
      config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("❌ Camera init failed: 0x%x\n", err);
    return;
  }

  sensor_t * s = esp_camera_sensor_get();
  if (s != nullptr) {
    s->set_vflip(s, 1);
    s->set_hmirror(s, 1);
    s->set_brightness(s, 1);
    s->set_contrast(s, 2);
  }

  Serial.println("✅ Camera configured");
}

void loop() {
  // NON fare nulla se il sistema non è inizializzato
  if (!systemInitialized) {
    delay(100);
    return;
  }
  
  readNodeMCU();
  
  // LOGICA SEMPLIFICATA: leggi comando e applica immediatamente
  String newCommand = getCommandFromFlask();
  
  if (newCommand.length() > 0) {
    // AGGIORNA SEMPRE il comando e il timestamp
    currentCommand = newCommand;
    lastCommandTime = millis();
    
    // ESEGUI IMMEDIATAMENTE
    executeCommand(currentCommand);
  }
  
  // TIMEOUT: se non arrivano comandi per troppo tempo, ferma
  checkCommandTimeout();
  
  sendVideoFrame();
  
  delay(5);  // Veloce per responsività
}

void executeCommand(String cmd) {
  // NON STAMPARE SE È LO STESSO COMANDO (evita spam)
  if (cmd != lastActiveCommand) {
    Serial.printf("🎮 COMMAND: '%s'\n", cmd.c_str());
    lastActiveCommand = cmd;
  }
  
  if (cmd == "n") {
    digitalWrite(FLASH_LED_PIN, HIGH);
  } 
  else if (cmd == "m") {
    digitalWrite(FLASH_LED_PIN, LOW);
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
  else {
    // QUALSIASI ALTRO COMANDO (incluso "stop" o vuoto) = STOP
    stopMotors();
  }
}

void checkCommandTimeout() {
  unsigned long now = millis();
  
  // Se non arrivano comandi da troppo tempo, ferma tutto
  if (now - lastCommandTime > COMMAND_TIMEOUT) {
    if (motorsActive) {
      Serial.printf("⏰ TIMEOUT (%dms) - stopping\n", COMMAND_TIMEOUT);
      stopMotors();
    }
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
  for (int i = 0; i < motorPins.size(); i++) {
    ledcWrite(motorPins[i].pinEn, speed);
  }
}

// FUNZIONI MOVIMENTO - SEMPRE VELOCITÀ MASSIMA
void moveForward() {
  rotateMotor(RIGHT_MOTOR, FORWARD);
  rotateMotor(LEFT_MOTOR, FORWARD);
  setMotorSpeed(MAX_SPEED);  // SEMPRE 255
  motorsActive = true;
}

void moveBackward() {
  rotateMotor(RIGHT_MOTOR, BACKWARD);
  rotateMotor(LEFT_MOTOR, BACKWARD);
  setMotorSpeed(MAX_SPEED);  // SEMPRE 255
  motorsActive = true;
}

void turnLeft() {
  rotateMotor(RIGHT_MOTOR, FORWARD);
  rotateMotor(LEFT_MOTOR, BACKWARD);
  setMotorSpeed(MAX_SPEED);  // SEMPRE 255
  motorsActive = true;
}

void turnRight() {
  rotateMotor(RIGHT_MOTOR, BACKWARD);
  rotateMotor(LEFT_MOTOR, FORWARD);
  setMotorSpeed(MAX_SPEED);  // SEMPRE 255
  motorsActive = true;
}

void stopMotors() {
  rotateMotor(RIGHT_MOTOR, STOP);
  rotateMotor(LEFT_MOTOR, STOP);
  setMotorSpeed(0);
  motorsActive = false;
}

// Funzioni NodeMCU e network (invariate)
void readNodeMCU() {
  static char buffer[64];
  static uint8_t idx = 0;
  while (nodeSerial.available()) {
    char c = nodeSerial.read();
    if (c == '\n') {
      buffer[idx] = 0;
      parseNodeData(buffer);
      idx = 0;
    } else if (idx < sizeof(buffer) - 1 && c != '\r') {
      buffer[idx++] = c;
    }
  }
}

void parseNodeData(const char* data) {
  float lat, lon, temp, hum;
  if (sscanf(data, "%f,%f,%f,%f", &lat, &lon, &temp, &hum) == 4) {
    latitude = lat;
    longitude = lon;
    temperature = temp;
    humidity = hum;
  }
}

String getCommandFromFlask() {
  WiFiClient client;
  String command = "";
  if (client.connect(flask_server, flask_port)) {
    client.print("GET /get_command HTTP/1.1\r\n");
    client.print("Host: ");
    client.print(flask_server);
    client.print("\r\nConnection: close\r\n\r\n");
    
    unsigned long timeout = millis();
    String header = "";
    while (client.connected()) {
      if (client.available()) {
        char c = client.read();
        header += c;
        if (header.endsWith("\r\n\r\n")) break;
      }
      if (millis() - timeout > 200) {  // Timeout ridotto per velocità
        client.stop();
        return "";
      }
    }
    
    String body = "";
    timeout = millis();
    while (client.connected()) {
      if (client.available()) {
        char c = client.read();
        body += c;
      } else if (millis() - timeout > 50) {  // Timeout ridotto
        break;
      }
    }
    body.trim();
    client.stop();
    return body;
  }
  return "";
}

void sendVideoFrame() {
  camera_fb_t * fb = esp_camera_fb_get();
  if (!fb) {
    return;
  }

  WiFiClient client;
  if (client.connect(flask_server, flask_port)) {
    client.print("POST /upload HTTP/1.1\r\n");
    client.print("Host: ");
    client.print(flask_server);
    client.print("\r\n");
    client.print("Content-Type: image/jpeg\r\n");
    client.print("Content-Length: ");
    client.print(fb->len);
    
    client.print("\r\nX-GPS: ");
    client.print(latitude, 6);
    client.print(",");
    client.print(longitude, 6);
    client.print("\r\nX-TEMP: ");
    client.print(temperature, 2);
    client.print(",");
    client.print(humidity, 2);
    client.print("\r\n\r\n");
    
    client.write(fb->buf, fb->len);
    client.stop();
  }
  esp_camera_fb_return(fb);
}
