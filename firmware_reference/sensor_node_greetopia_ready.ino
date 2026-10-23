/*
  !!! DEPRECATED - DO NOT FLASH TO A REAL PUMP !!!
  Replaced by firmware/sensor_node (v2). Known problems of this variant:
   - the MQTT handler no longer checks !pumpRunning, so every new "ON" restarts the timer and repeated commands keep the pump on;
   - the 15 s cutoff sits behind blocking Wi-Fi/MQTT reconnect loops;
   - HTTP mode has no command channel and HTTPS has no certificate handling;
   - based on the older sensor firmware (3000/1200, no power-switched probes, no calibration mode).
  Kept only for reference.
*/
/*
  ============================================================
  SMART IRRIGATION - SENSOR NODE FIRMWARE (ESP32)
  Greetopia Ready: Supports Authenticated MQTT and Direct HTTP API
  ============================================================
  Features:
    1. Reads 3-depth capacitive soil sensors (surface, mid, root) + DHT22 (temp/humidity).
    2. Supports Authenticated MQTT: Broker URL, Port, Username, and Password.
    3. Supports Direct HTTP Telemetry: Can post directly to Greetopia (e.g. Vercel)
       via REST API without needing an external MQTT broker!
    4. Hardware safety pump cutoff (hardcoded max duration).

  LIBRARIES REQUIRED (Arduino IDE > Tools > Manage Libraries):
    - "PubSubClient" by Nick O'Leary (for MQTT)
    - "DHT sensor library" by Adafruit (for temp/humidity)
    - "Adafruit Unified Sensor" by Adafruit
    - "ArduinoJson" by Benoît Blanchon (for HTTP JSON telemetry)
  ============================================================
*/

#include <WiFi.h>
#include <PubSubClient.h>
#include <HTTPClient.h>
#include <DHT.h>

// ============================================================
// 1. NETWORK & AUTHENTICATION CONFIGURATION
// ============================================================
const char* WIFI_SSID     = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

const char* PLANT_ID      = "plant01"; // Unique identifier for this plant

// --- MQTT Broker Configuration ---
// Set USE_MQTT to true if using an MQTT broker (e.g., HiveMQ, EMQX, Mosquitto)
const bool  USE_MQTT       = true;
const char* MQTT_BROKER    = "broker.hivemq.com"; // Your broker host
const int   MQTT_PORT      = 1883;                 // 1883 (TCP) or 8883 (TLS)
const char* MQTT_USERNAME  = "";                   // MQTT username (leave empty if none)
const char* MQTT_PASSWORD  = "";                   // MQTT password (leave empty if none)

// --- HTTP REST API Configuration ---
// Set USE_HTTP to true if you want to post directly to your Greetopia API (e.g. Vercel)
const bool  USE_HTTP       = false;
const char* HTTP_API_URL   = "https://greetopia.vercel.app/api/v1/plants/plant01/telemetry";
const char* DEVICE_TOKEN   = ""; // Optional: matches DEVICE_UPLOAD_TOKEN in backend .env

// ============================================================
// 2. HARDWARE PIN SETUP
// ============================================================
#define SOIL_PIN_SURFACE  34   // ~2-3cm deep (surface)
#define SOIL_PIN_MID      35   // ~7-8cm deep (mid-depth)
#define SOIL_PIN_ROOT     32   // ~15cm deep (root-zone)
#define DHT_PIN            4   // DHT22 data pin
#define RELAY_PIN         26   // Relay pin controlling pump
#define DHTTYPE        DHT22

// ============================================================
// 3. OPERATIONAL SETTINGS
// ============================================================
const unsigned long READ_INTERVAL_MS = 10000; // Read and publish every 10 seconds
const unsigned long MAX_PUMP_RUN_MS  = 15000; // Firmware safety limit: 15 seconds max
const bool RELAY_ACTIVE_LOW = true;          // Most relay modules trigger on LOW

const int SOIL_DRY_VALUE = 3000; // Calibrate in dry air
const int SOIL_WET_VALUE = 1200; // Calibrate submerged in water

// MQTT Topics
String TOPIC_SOIL_SURFACE = String("plants/") + PLANT_ID + "/soil/surface";
String TOPIC_SOIL_MID     = String("plants/") + PLANT_ID + "/soil/mid";
String TOPIC_SOIL_ROOT    = String("plants/") + PLANT_ID + "/soil/root";
String TOPIC_TEMP         = String("plants/") + PLANT_ID + "/temp";
String TOPIC_HUMIDITY     = String("plants/") + PLANT_ID + "/humidity";
String TOPIC_STATUS       = String("plants/") + PLANT_ID + "/status";
String TOPIC_COMMAND      = String("plants/") + PLANT_ID + "/water";

// Hardware objects
WiFiClient espClient;
PubSubClient mqttClient(espClient);
DHT dht(DHT_PIN, DHTTYPE);

unsigned long lastReadTime = 0;
bool pumpRunning = false;
unsigned long pumpStartTime = 0;
unsigned long pumpRunDurationMs = 0;

void pumpOn() {
  digitalWrite(RELAY_PIN, RELAY_ACTIVE_LOW ? LOW : HIGH);
}

void pumpOff() {
  digitalWrite(RELAY_PIN, RELAY_ACTIVE_LOW ? HIGH : LOW);
}

int readSoilPercent(int pin) {
  int raw = analogRead(pin);
  int pct = map(raw, SOIL_DRY_VALUE, SOIL_WET_VALUE, 0, 100);
  return constrain(pct, 0, 100);
}

void connectWiFi() {
  Serial.print("Connecting to WiFi: ");
  Serial.println(WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected! IP address: ");
  Serial.println(WiFi.localIP());
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String msg = "";
  for (unsigned int i = 0; i < length; i++) {
    msg += (char)payload[i];
  }
  msg.trim();
  Serial.printf("MQTT Message arrived on [%s]: %s\n", topic, msg.c_str());

  if (String(topic) == TOPIC_COMMAND && msg.startsWith("ON")) {
    unsigned long requestedMs = MAX_PUMP_RUN_MS;
    int colonIndex = msg.indexOf(':');
    if (colonIndex != -1) {
      int seconds = msg.substring(colonIndex + 1).toInt();
      if (seconds > 0) {
        requestedMs = (unsigned long)seconds * 1000UL;
      }
    }
    pumpRunDurationMs = min(requestedMs, MAX_PUMP_RUN_MS);
    Serial.printf("Watering command accepted. Pump ON for %lu ms\n", pumpRunDurationMs);
    pumpOn();
    pumpRunning = true;
    pumpStartTime = millis();
    if (USE_MQTT && mqttClient.connected()) {
      mqttClient.publish(TOPIC_STATUS.c_str(), "watering");
    }
  }
}

void connectMQTT() {
  while (!mqttClient.connected()) {
    Serial.print("Connecting to MQTT broker: ");
    Serial.println(MQTT_BROKER);
    String clientId = String("esp32-") + PLANT_ID + "-" + String(random(0xffff), HEX);

    bool connected = false;
    // Connect with or without authentication based on credentials provided
    if (strlen(MQTT_USERNAME) > 0) {
      connected = mqttClient.connect(clientId.c_str(), MQTT_USERNAME, MQTT_PASSWORD);
    } else {
      connected = mqttClient.connect(clientId.c_str());
    }

    if (connected) {
      Serial.println("MQTT connected successfully!");
      mqttClient.subscribe(TOPIC_COMMAND.c_str(), 1);
      mqttClient.publish(TOPIC_STATUS.c_str(), "idle");
    } else {
      Serial.print("MQTT connection failed, state rc=");
      Serial.print(mqttClient.state());
      Serial.println(". Retrying in 4 seconds...");
      delay(4000);
    }
  }
}

void sendHttpTelemetry(int surface, int mid, int root, float temp, float hum) {
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http;
  http.begin(HTTP_API_URL);
  http.addHeader("Content-Type", "application/json");
  if (strlen(DEVICE_TOKEN) > 0) {
    http.addHeader("X-Device-Token", DEVICE_TOKEN);
  }

  String json = "{";
  json += "\"soil_surface\":" + String(surface) + ",";
  json += "\"soil_mid\":" + String(mid) + ",";
  json += "\"soil_root\":" + String(root);
  if (!isnan(temp)) {
    json += ",\"temperature_c\":" + String(temp, 1);
  }
  if (!isnan(hum)) {
    json += ",\"humidity_pct\":" + String(hum, 1);
  }
  json += "}";

  int httpCode = http.POST(json);
  if (httpCode > 0) {
    Serial.printf("HTTP telemetry sent, response code: %d\n", httpCode);
  } else {
    Serial.printf("HTTP telemetry failed, error: %s\n", http.errorToString(httpCode).c_str());
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  pumpOff();
  pinMode(RELAY_PIN, OUTPUT);
  pumpOff();

  dht.begin();
  connectWiFi();

  if (USE_MQTT) {
    mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
    mqttClient.setCallback(mqttCallback);
  }
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  if (USE_MQTT) {
    if (!mqttClient.connected()) {
      connectMQTT();
    }
    mqttClient.loop();
  }

  // Safety cutoff: never exceed pumpRunDurationMs
  if (pumpRunning && (millis() - pumpStartTime >= pumpRunDurationMs)) {
    pumpOff();
    pumpRunning = false;
    Serial.println("Pump turned OFF (safety cutoff / cycle complete).");
    if (USE_MQTT && mqttClient.connected()) {
      mqttClient.publish(TOPIC_STATUS.c_str(), "idle");
    }
  }

  // Periodic sensor read and publish
  if (millis() - lastReadTime >= READ_INTERVAL_MS) {
    lastReadTime = millis();

    int surface = readSoilPercent(SOIL_PIN_SURFACE);
    int mid     = readSoilPercent(SOIL_PIN_MID);
    int root    = readSoilPercent(SOIL_PIN_ROOT);

    float temp = dht.readTemperature();
    float hum  = dht.readHumidity();

    Serial.printf("Readings -> Surface: %d%% | Mid: %d%% | Root: %d%% | Temp: %.1fC | Hum: %.1f%%\n",
                  surface, mid, root, isnan(temp) ? 0.0 : temp, isnan(hum) ? 0.0 : hum);

    // 1. Publish via MQTT if enabled
    if (USE_MQTT && mqttClient.connected()) {
      mqttClient.publish(TOPIC_SOIL_SURFACE.c_str(), String(surface).c_str());
      mqttClient.publish(TOPIC_SOIL_MID.c_str(),     String(mid).c_str());
      mqttClient.publish(TOPIC_SOIL_ROOT.c_str(),    String(root).c_str());

      if (!isnan(temp)) {
        mqttClient.publish(TOPIC_TEMP.c_str(), String(temp, 1).c_str());
      }
      if (!isnan(hum)) {
        mqttClient.publish(TOPIC_HUMIDITY.c_str(), String(hum, 1).c_str());
      }
    }

    // 2. Publish via HTTP REST API if enabled
    if (USE_HTTP) {
      sendHttpTelemetry(surface, mid, root, temp, hum);
    }
  }
}
