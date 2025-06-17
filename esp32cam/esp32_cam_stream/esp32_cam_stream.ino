#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>

// Replace with your network credentials
const char* ssid = "yoyo";
const char* password = "commitciao";

// Select camera model
#define CAMERA_MODEL_AI_THINKER // Has PSRAM
#include "camera_pins.h"

// Definizione dei pin
#define ENA 14
#define ENB 15
#define IN1 13
#define IN2 12
#define IN3 3
#define IN4 1

void setup() {
  Serial.begin(115200);
  while (!Serial) {
    delay(100);
  }
  Serial.println("Starting setup...");

  // Impostazione dei pin del motore
  pinMode(ENA, OUTPUT);
  pinMode(ENB, OUTPUT);
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);

  // Connessione alla rete Wi-Fi
  Serial.print("Connecting to WiFi...");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("WiFi connected");

  // Configurazione della videocamera
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
  config.frame_size = FRAMESIZE_VGA;
  config.pixel_format = PIXFORMAT_JPEG;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality = 10;
  config.fb_count = 2;

  // Inizializzazione della videocamera
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x", err);
    return;
  }

  // Ottenimento del sensore della videocamera
  sensor_t * s = esp_camera_sensor_get();
  s->set_vflip(s, 1); // Flip vertically
  s->set_hmirror(s, 1); // Flip horizontally

  Serial.println("Setup completed.");
}

void loop() {
  // Controllo del movimento tramite comandi HTTP
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("WiFi connected, checking for commands...");
    HTTPClient http;
    http.begin("http://192.168.187.148:8080/get_command");
    int httpCode = http.GET();

    if (httpCode > 0) {
      String payload = http.getString();
      Serial.println("Received command: " + payload);
      if (payload == "avanti") {
        avanti();
      } else if (payload == "indietro") {
        indietro();
      } else if (payload == "destra") {
        sterzaDestra();
      } else if (payload == "sinistra") {
        sterzaSinistra();
      }
    } else {
      Serial.printf("Error on HTTP request: %s\n", http.errorToString(httpCode).c_str());
    }

    http.end();
  } else {
    Serial.println("WiFi not connected");
  }

  // Aggiungiamo debug per la fotocamera
  Serial.println("Capturing image...");
  camera_fb_t * fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Camera capture failed");
    return;
  }

  WiFiClient client;
  if (!client.connect("192.168.187.148", 8080)) {
    Serial.println("Connection to server failed");
    esp_camera_fb_return(fb);
    return;
  }

  // Make a HTTP POST request
  client.println("POST /upload HTTP/1.1");
  client.println("Host: 192.168.187.148");
  client.println("Content-Type: image/jpeg");
  client.print("Content-Length: ");
  client.println(fb->len);
  client.println();
  client.write(fb->buf, fb->len);

  esp_camera_fb_return(fb);
  Serial.println("Image sent to server");

  delay(100); // delay for 100 ms
}

void avanti() {
  Serial.println("Moving forward");
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
  ledcWrite(0, 255);
  ledcWrite(1, 255);
}

void indietro() {
  Serial.println("Moving backward");
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, HIGH);
  ledcWrite(0, 255);
  ledcWrite(1, 255);
}

void sterzaDestra() {
  Serial.println("Turning right");
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
  ledcWrite(0, 255);
  ledcWrite(1, 100); // Ridurre potenza al motore posteriore sinistro
}

void sterzaSinistra() {
  Serial.println("Turning left");
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
  ledcWrite(0, 100); // Ridurre potenza al motore posteriore destro
  ledcWrite(1, 255);
}