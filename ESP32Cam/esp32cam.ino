#include "esp_camera.h"
#include <WiFi.h>

// ===========================
// WiFi Configuration
// ===========================
const char* ssid = "Yubu";
const char* password = "Geova666";
const char* flask_server = "10.158.41.187";
const int flask_port = 5000;

// ===========================
// CAMERA PINS (AI Thinker)
// ===========================
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

// ===========================
// FLASH LED (AI Thinker)
#define FLASH_LED_PIN 4

// ===========================
// MOTOR PINS (evitando conflitti camera)
#define ENA 2     // PWM motore A
#define ENB 16    // PWM motore B  
#define IN1 14    // Controllo motore A
#define IN2 15    // Controllo motore A
#define IN3 13    // Controllo motore B
#define IN4 12    // Controllo motore B

// ===========================
// UART PINS for NodeMCU communication
#define NODEMCU_RX 3  // U0RXD (ESP32-CAM RX) -- collegato a TX NodeMCU
#define NODEMCU_TX 1  // U0TXD (ESP32-CAM TX) -- collegato a RX NodeMCU

// ===========================
// PWM Configuration
#define PWM_FREQ 1000
#define PWM_RESOLUTION 8

#include <HardwareSerial.h>
HardwareSerial nodeSerial(1); // UART0, ma con pin swap

String nodeData = "";   // Ricevi dati aggregati da NodeMCU: "lat,lon,temp,hum"
float latitude = 0.0, longitude = 0.0, temperature = 0.0, humidity = 0.0;

String currentCommand = "";
unsigned long lastCommandTime = 0;
const unsigned long COMMAND_TIMEOUT = 2000; // 2 secondi timeout

void setup() {
  Serial.begin(115200);
  Serial.println("=== ESP32-CAM FULL SYSTEM + UART NodeMCU ===");

  // Setup Motor Pins
  setupMotors();
  // WiFi Connection
  setupWiFi();
  // Camera Setup (ottimizzata)
  setupCamera();
  // UART Setup (NodeMCU)
  nodeSerial.begin(9600, SERIAL_8N1, NODEMCU_RX, NODEMCU_TX);

  Serial.println("=== SYSTEM READY ===");
  Serial.println("📹 Video streaming: ON");
  Serial.println("🚗 Motor control: ON");
  Serial.println("📡 UART NodeMCU: ON");
  // Setup Flash LED
  pinMode(FLASH_LED_PIN, OUTPUT);
  digitalWrite(FLASH_LED_PIN, LOW);  // Inizialmente spento
  Serial.println("💡 Flash LED: OFF (default)");
}

void setupMotors() {
  Serial.println("🔧 Setting up motors...");
  ledcAttach(ENA, PWM_FREQ, PWM_RESOLUTION);
  ledcAttach(ENB, PWM_FREQ, PWM_RESOLUTION);
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  stopMotors();
  Serial.println("✅ Motors configured");
}

void setupWiFi() {
  Serial.println("🌐 Connecting to WiFi...");
  WiFi.begin(ssid, password);
  WiFi.setSleep(false);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
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

  // AUTODETECT PSRAM
  if(psramFound()) {
      config.frame_size = FRAMESIZE_SVGA; // 800x600
      config.jpeg_quality = 8;
      config.fb_count = 2;
      config.fb_location = CAMERA_FB_IN_PSRAM;
      config.grab_mode = CAMERA_GRAB_LATEST;
      Serial.println("PSRAM FOUND: SVGA, double buffer");
  } else {
      config.frame_size = FRAMESIZE_VGA; // 640x480
      config.jpeg_quality = 10;
      config.fb_count = 1;
      config.fb_location = CAMERA_FB_IN_DRAM;
      config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
      Serial.println("NO PSRAM: VGA, single buffer");
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("❌ Camera init failed: 0x%x\n", err);
    return;
  }

  // Camera optimizations
  sensor_t * s = esp_camera_sensor_get();
  if (s == nullptr) {
    Serial.println("❌ Camera sensor not available!");
    return;
  }
  s->set_vflip(s, 1);
  s->set_hmirror(s, 1);
  s->set_brightness(s, 1);
  s->set_contrast(s, 2);
  s->set_saturation(s, 1);
  s->set_sharpness(s, 1);

  Serial.println("✅ Camera configured (SVGA, qualità 8, double buffer)");
}

void loop() {
  unsigned long t0 = millis();
  readNodeMCU();
  unsigned long t1 = millis();
  String newCommand = getCommandFromFlask();
  if (newCommand.length() > 0) {
    currentCommand = newCommand;
    lastCommandTime = millis();
    Serial.printf("📨 New command: '%s'\n", currentCommand.c_str());
  }
  unsigned long t2 = millis();
  executeMotorCommand();
  unsigned long t3 = millis();

  Serial.printf("Timing: UART=%lums, GetCmd=%lums, MotorCmd=%lums\n", t1-t0, t2-t1, t3-t2);

  unsigned long t_send0 = millis();
  sendVideoFrame();
  unsigned long t_send1 = millis();
  Serial.printf("Timing: sendVideoFrame=%lums (Full loop=%lums)\n", t_send1-t_send0, t_send1-t0);

  delay(10); // o quello che vuoi
}

// ============ UART DA NODEMCU ==============
// Ricevi i dati dalla NodeMCU: es. "45.12345,9.12345,24.5,60.1"
void readNodeMCU() {
  static char buffer[64];
  static uint8_t idx = 0;
  while (nodeSerial.available()) {
    char c = nodeSerial.read();
    if (c == '\n') {
      buffer[idx] = 0; // chiusura stringa
      parseNodeData(buffer); // Passa la stringa completa
      idx = 0;
    } else if (idx < sizeof(buffer) - 1 && c != '\r') {
      buffer[idx++] = c;
    }
  }
}

void parseNodeData(const char* data) {
  // Attenzione: formato atteso "lat,lon,temp,hum"
  float lat, lon, temp, hum;
  if (sscanf(data, "%f,%f,%f,%f", &lat, &lon, &temp, &hum) == 4) {
    latitude = lat;
    longitude = lon;
    temperature = temp;
    humidity = hum;
  }
}

// ============ NETWORK & CONTROL =============

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
    // Leggi header riga per riga, senza bloccare
    while (client.connected()) {
      if (client.available()) {
        char c = client.read();
        header += c;
        // Quando trovi fine header, esci
        if (header.endsWith("\r\n\r\n")) break;
      }
      if (millis() - timeout > 300) {
        client.stop();
        return "";
      }
    }
    // Ora leggi solo il body
    String body = "";
    timeout = millis();
    while (client.connected()) {
      if (client.available()) {
        char c = client.read();
        body += c;
      } else if (millis() - timeout > 100) {
        break;
      }
    }
    body.trim();
    client.stop();
    return body;
  }
  return "";
}

void executeMotorCommand() {
  if (millis() - lastCommandTime > COMMAND_TIMEOUT) {
    if (currentCommand != "") {
      currentCommand = "";
      stopMotors();
      Serial.println("⏰ Command timeout - stopping motors");
    }
    return;
  }
  if (currentCommand == "avanti" || currentCommand == "a") {
    moveForward();
  } else if (currentCommand == "indietro" || currentCommand == "i") {
    moveBackward();
  } else if (currentCommand == "sinistra" || currentCommand == "s")  {
    turnLeft();
  } else if (currentCommand == "destra" || currentCommand == "d") {
    turnRight();
  }else if (currentCommand == "n_flash_on" || currentCommand == "n") {
    digitalWrite(FLASH_LED_PIN, HIGH);
    Serial.println("💡 Flash LED: ON");
  } else if (currentCommand == "m_flash_off" || currentCommand == "m") {
    digitalWrite(FLASH_LED_PIN, LOW);
    Serial.println("💡 Flash LED: OFF");
  }  else {
    stopMotors();
  }
}

void sendVideoFrame() {
  camera_fb_t * fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("❌ Camera capture failed");
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
    // Invio posizione GPS e temperatura come header custom
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

// MOTOR CONTROL FUNCTIONS (NUOVA API)
void moveForward() {
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
  ledcWrite(ENA, 220);
  ledcWrite(ENB, 220);
}

void moveBackward() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, HIGH);
  ledcWrite(ENA, 220);
  ledcWrite(ENB, 220);
}

void turnLeft() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
  ledcWrite(ENA, 180);
  ledcWrite(ENB, 180);
}

void turnRight() {
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, HIGH);
  ledcWrite(ENA, 180);
  ledcWrite(ENB, 180);
}

void stopMotors() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
  ledcWrite(ENA, 0);
  ledcWrite(ENB, 0);
}