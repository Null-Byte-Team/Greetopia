/*
  ============================================================
  SMART IRRIGATION - PLANT NODE FIRMWARE
  (camera node and leaf-wetness sensor removed — soil x3 + DHT22 + pump only)
  ============================================================
  What this does, in plain words:
    1. Connects your ESP32 to your WiFi.
    2. Reads the soil moisture sensor and the DHT22 (temp/humidity).
    3. Sends those readings to the cloud every 10 seconds using MQTT
       (think of MQTT as a mailbox: this device drops letters in,
       and your cloud/app picks them up).
    4. Listens for a "water now" command from the cloud/app, and
       when it gets one, turns the pump on for a set number of
       seconds, then turns it off automatically (with a safety
       cutoff so it can never run forever by mistake).

  BEFORE YOU UPLOAD:
    - Fill in your WiFi name + password below (WIFI_SSID / WIFI_PASSWORD)
    - Fill in your MQTT broker address (MQTT_BROKER) — for testing you
      can get a free one instantly at https://www.hivemq.com/mqtt/public-mqtt-broker/
      (use broker.hivemq.com, port 1883, for testing only — it's public,
      don't send anything private through it)
    - Give this specific plant a unique name (PLANT_ID) if you'll have
      more than one node later

  LIBRARIES YOU NEED (install via Arduino IDE > Tools > Manage Libraries):
    - "PubSubClient" by Nick O'Leary        (MQTT)
    - "DHT sensor library" by Adafruit      (temp/humidity)
    - "Adafruit Unified Sensor"             (required by the DHT library)
    - ESP32 board support installed via Boards Manager (search "esp32")
  ============================================================
*/

#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>

// ---------- 1. FILL THESE IN ----------
const char* WIFI_SSID     = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* MQTT_BROKER   = "broker.hivemq.com";   // swap for your own broker later
const int   MQTT_PORT     = 1883;
const char* PLANT_ID      = "plant01";             // unique name for this node

// ---------- 2. PIN SETUP (matches the wiring guide) ----------
// UPGRADE: three soil sensors at different depths instead of one, so the
// system can see how water actually moves down through the soil over time.
#define SOIL_PIN_SURFACE  34   // ~2-3cm deep: reacts fastest, dries fastest
#define SOIL_PIN_MID      35   // ~7-8cm deep: mid root zone
#define SOIL_PIN_ROOT      32   // ~15cm deep: near the main roots, most important for watering decisions
#define DHT_PIN    4    // DHT22 data pin
#define RELAY_PIN  26   // relay signal pin (controls the pump)
#define DHTTYPE    DHT22

// ---------- 3. TUNABLE SETTINGS ----------
const unsigned long READ_INTERVAL_MS   = 10000;   // read + publish every 10 sec
const unsigned long MAX_PUMP_RUN_MS    = 15000;   // safety cutoff: pump never runs longer than 15 sec per command
// Most cheap blue 1-channel relay modules are "active LOW": the relay switches ON when the
// signal pin goes LOW. If yours clicks ON at boot while the pump is unplugged, set this to false.
// (In the Wokwi simulator with a plain LED, set it to false.)
const bool RELAY_ACTIVE_LOW = true;
const int SOIL_DRY_VALUE  = 3000;                 // sensor reading in dry air (calibrate this!)
const int SOIL_WET_VALUE  = 1200;                 // sensor reading fully in water (calibrate this!)

// ---------- MQTT TOPICS (the "mailbox addresses") ----------
String TOPIC_SOIL_SURFACE = String("plants/") + PLANT_ID + "/soil/surface";
String TOPIC_SOIL_MID     = String("plants/") + PLANT_ID + "/soil/mid";
String TOPIC_SOIL_ROOT    = String("plants/") + PLANT_ID + "/soil/root";
String TOPIC_TEMP     = String("plants/") + PLANT_ID + "/temp";
String TOPIC_HUMIDITY = String("plants/") + PLANT_ID + "/humidity";
String TOPIC_STATUS   = String("plants/") + PLANT_ID + "/status";
String TOPIC_COMMAND  = String("plants/") + PLANT_ID + "/water"; // cloud sends "ON" here to trigger watering

// ---------- internals, no need to touch ----------
WiFiClient espClient;
PubSubClient mqttClient(espClient);
DHT dht(DHT_PIN, DHTTYPE);

unsigned long lastReadTime = 0;
bool pumpRunning = false;
unsigned long pumpStartTime = 0;
unsigned long pumpRunDurationMs = MAX_PUMP_RUN_MS;  // can be overridden per command, see below

void pumpOn()  { digitalWrite(RELAY_PIN, RELAY_ACTIVE_LOW ? LOW  : HIGH); }
void pumpOff() { digitalWrite(RELAY_PIN, RELAY_ACTIVE_LOW ? HIGH : LOW);  }

int readSoilPercent(int pin) {
  int raw = analogRead(pin);
  int percent = map(raw, SOIL_DRY_VALUE, SOIL_WET_VALUE, 0, 100);
  return constrain(percent, 0, 100);
}

void connectWiFi() {
  Serial.print("Connecting to WiFi");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected! IP address: " + WiFi.localIP().toString());
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String message;
  for (unsigned int i = 0; i < length; i++) message += (char)payload[i];
  Serial.println("Message on [" + String(topic) + "]: " + message);

  // UPGRADE: supports a control-panel "manual water" button.
  // Payload can be plain "ON" (uses the default duration) or
  // "ON:8" to run for a custom 8 seconds — this lets the app/site
  // offer a duration slider instead of only a fixed watering time.
  // Whatever number comes in, it's still capped at MAX_PUMP_RUN_MS
  // for safety -- a command can never make the pump run longer than that.
  if (String(topic) == TOPIC_COMMAND && message.startsWith("ON") && !pumpRunning) {
    unsigned long requestedMs = MAX_PUMP_RUN_MS;
    int colonIndex = message.indexOf(':');
    if (colonIndex != -1) {
      int seconds = message.substring(colonIndex + 1).toInt();
      if (seconds > 0) requestedMs = (unsigned long)seconds * 1000UL;
    }
    pumpRunDurationMs = min(requestedMs, MAX_PUMP_RUN_MS);

    Serial.printf("Watering command received. Pump ON for %lu ms.\n", pumpRunDurationMs);
    pumpOn();
    pumpRunning = true;
    pumpStartTime = millis();
    mqttClient.publish(TOPIC_STATUS.c_str(), "watering");
  }
}

void connectMQTT() {
  while (!mqttClient.connected()) {
    Serial.print("Connecting to MQTT broker...");
    String clientId = String("esp32-") + PLANT_ID;
    if (mqttClient.connect(clientId.c_str())) {
      Serial.println("connected!");
      mqttClient.subscribe(TOPIC_COMMAND.c_str());
    } else {
      Serial.print("failed, rc=");
      Serial.print(mqttClient.state());
      Serial.println(" retrying in 3 seconds");
      delay(3000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  pumpOff();                      // set the OFF level first...
  pinMode(RELAY_PIN, OUTPUT);     // ...then make the pin an output (pump stays OFF at boot)
  pumpOff();
  dht.begin();

  connectWiFi();
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setCallback(mqttCallback);
}

void loop() {
  if (!mqttClient.connected()) connectMQTT();
  mqttClient.loop();

  // Safety cutoff: never let the pump run past MAX_PUMP_RUN_MS
  if (pumpRunning && (millis() - pumpStartTime >= pumpRunDurationMs)) {
    pumpOff();
    pumpRunning = false;
    Serial.println("Pump OFF (safety cutoff / cycle complete).");
    mqttClient.publish(TOPIC_STATUS.c_str(), "idle");
  }

  // Read and publish sensor data every READ_INTERVAL_MS
  if (millis() - lastReadTime >= READ_INTERVAL_MS) {
    lastReadTime = millis();

    int surfacePercent = readSoilPercent(SOIL_PIN_SURFACE);
    int midPercent     = readSoilPercent(SOIL_PIN_MID);
    int rootPercent    = readSoilPercent(SOIL_PIN_ROOT);

    float temp = dht.readTemperature();
    float humidity = dht.readHumidity();

    Serial.printf("Soil surface:%d%% mid:%d%% root:%d%%  Temp:%.1fC  Humidity:%.1f%%\n",
                  surfacePercent, midPercent, rootPercent, temp, humidity);

    mqttClient.publish(TOPIC_SOIL_SURFACE.c_str(), String(surfacePercent).c_str());
    mqttClient.publish(TOPIC_SOIL_MID.c_str(),     String(midPercent).c_str());
    mqttClient.publish(TOPIC_SOIL_ROOT.c_str(),    String(rootPercent).c_str());
    if (!isnan(temp))     mqttClient.publish(TOPIC_TEMP.c_str(), String(temp).c_str());
    if (!isnan(humidity)) mqttClient.publish(TOPIC_HUMIDITY.c_str(), String(humidity).c_str());
  }
}
