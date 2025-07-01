#include <TinyGPSPlus.h>
#include <DHT.h>
#include <SoftwareSerial.h>

// Pinout
#define GPS_RX_PIN D1 // NodeMCU RX <-- GPS TX
#define DHT_PIN D2
#define DHT_TYPE DHT11

SoftwareSerial gpsSerial(GPS_RX_PIN, -1); // Solo RX, nessun TX
TinyGPSPlus gps;
DHT dht(DHT_PIN, DHT_TYPE);

void setup() {
  Serial.begin(9600);         // UART verso ESP32-CAM
  gpsSerial.begin(9600);      // GPS
  dht.begin();
}

void loop() {
  // Lettura GPS
  while (gpsSerial.available()) {
    char c = gpsSerial.read();
    gps.encode(c);
  }

  // Lettura DHT11 e invio ogni 2s
  static unsigned long lastSend = 0;
  if (millis() - lastSend > 2000) {
    lastSend = millis();
    float lat = gps.location.isValid() ? gps.location.lat() : 0.0;
    float lon = gps.location.isValid() ? gps.location.lng() : 0.0;
    float temp = dht.readTemperature();
    float hum  = dht.readHumidity();
    Serial.print(lat, 6); Serial.print(",");
    Serial.print(lon, 6); Serial.print(",");
    Serial.print(temp, 2); Serial.print(",");
    Serial.print(hum, 2); Serial.println();
  }
}