/*
  ============================================================
  SMART IRRIGATION - SENSOR NODE FIRMWARE (ESP32 DevKit, 30-pin)
  ============================================================
  Reads 3 soil sensors (resistive, 40 EGP type) + DHT22, sends the
  numbers over WiFi (MQTT), and runs the pump when told to.

  HOW TO USE (details are in the instruction book):
    STEP 1. Fill in the 5 lines under "1. FILL THESE IN".
    STEP 2. Leave CALIBRATION_MODE = true, upload, open Serial Monitor
            (115200). Write down the raw numbers (dry vs wet).
    STEP 3. Type those numbers into the calibration section (4).
    STEP 4. Set CALIBRATION_MODE = false, upload again. Done.

  LIBRARIES (Tools > Manage Libraries): PubSubClient, DHT sensor
  library, Adafruit Unified Sensor.   Board: "ESP32 Dev Module".
  ============================================================
*/

#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>

// ---------- 1. FILL THESE IN ----------
const char* WIFI_SSID     = "YOUR_WIFI_NAME";      // must be a 2.4GHz network
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* MQTT_BROKER   = "broker.hivemq.com";   // public test broker (anyone can see it!)
const int   MQTT_PORT     = 1883;
const char* PLANT_ID      = "plant01";             // CHANGE to something unique, e.g. "plant_k7x2q9"
                                                   // (camera firmware must use the SAME name)

// ---------- 2. MODE ----------
const bool CALIBRATION_MODE = true;   // true = just print raw sensor numbers (no WiFi, pump stays OFF)

// ---------- 3. PINS (match the instruction book) ----------
#define DHT_PIN    4
#define RELAY_PIN  26
#define DHTTYPE    DHT22
// Soil sensor signal (AO) pins: surface, mid, root
const int SOIL_ADC_PINS[3] = {34, 35, 32};
// Each soil sensor gets its VCC from its own pin, switched ON only while reading.
// (This makes the cheap sensors last much longer. If you wired VCC to the 3.3V rail
//  instead, the code still works, it just won't save the sensors.)
const int SOIL_PWR_PINS[3] = {25, 27, 14};

// ---------- 4. CALIBRATION (fill in AFTER calibration mode) ----------
// For each sensor: raw number in DRY soil/air, and raw number in WET soil (just watered).
// Order: {surface, mid, root}. These are starting guesses, replace them!
const int SOIL_DRY_VALUE[3] = {4095, 4095, 4095};
const int SOIL_WET_VALUE[3] = {1500, 1500, 1500};

// ---------- 5. SETTINGS ----------
// Most blue 1-channel relay modules switch ON when the signal goes LOW ("active low").
// If your relay clicks ON at power-up with nothing sent, set this to false.
const bool RELAY_ACTIVE_LOW = true;
const unsigned long READ_INTERVAL_MS = 10000;   // send readings every 10 seconds
const unsigned long MAX_PUMP_RUN_MS  = 15000;   // safety: pump NEVER runs longer than 15 s per command

// ---------- MQTT topics ----------
String TOPIC_SOIL_SURFACE = String("plants/") + PLANT_ID + "/soil/surface";
String TOPIC_SOIL_MID     = String("plants/") + PLANT_ID + "/soil/mid";
String TOPIC_SOIL_ROOT    = String("plants/") + PLANT_ID + "/soil/root";
String TOPIC_TEMP         = String("plants/") + PLANT_ID + "/temp";
String TOPIC_HUMIDITY     = String("plants/") + PLANT_ID + "/humidity";
String TOPIC_STATUS       = String("plants/") + PLANT_ID + "/status";
String TOPIC_COMMAND      = String("plants/") + PLANT_ID + "/water";   // send "ON" or "ON:8" here

// ---------- internals, no need to touch ----------
WiFiClient espClient;
PubSubClient mqttClient(espClient);
DHT dht(DHT_PIN, DHTTYPE);

unsigned long lastReadTime = 0;
bool pumpRunning = false;
unsigned long pumpStartTime = 0;
unsigned long pumpRunDurationMs = MAX_PUMP_RUN_MS;

void pumpOn()  { digitalWrite(RELAY_PIN, RELAY_ACTIVE_LOW ? LOW  : HIGH); }
void pumpOff() { digitalWrite(RELAY_PIN, RELAY_ACTIVE_LOW ? HIGH : LOW);  }

// Reads one soil sensor: power it, wait, average 16 readings, power it off.
int readSoilRaw(int i) {
  digitalWrite(SOIL_PWR_PINS[i], HIGH);
  delay(100);
  long total = 0;
  for (int n = 0; n < 16; n++) {
    total += analogRead(SOIL_ADC_PINS[i]);
    delay(2);
  }
  digitalWrite(SOIL_PWR_PINS[i], LOW);
  return (int)(total / 16);
}

int readSoilPercent(int i) {
  int raw = readSoilRaw(i);
  if (SOIL_DRY_VALUE[i] == SOIL_WET_VALUE[i]) return 0;   // avoid dividing by zero
  int percent = map(raw, SOIL_DRY_VALUE[i], SOIL_WET_VALUE[i], 0, 100);
  return constrain(percent, 0, 100);
}

void runCalibrationMode() {
  Serial.println();
  Serial.println("=== CALIBRATION MODE (no WiFi, pump OFF) ===");
  Serial.println("Write down each sensor's number in DRY soil and in WET soil.");
  while (true) {
    float t = dht.readTemperature();
    float h = dht.readHumidity();
    Serial.printf("RAW  surface=%4d  mid=%4d  root=%4d   |  temp=%.1f C  humidity=%.1f %%\n",
                  readSoilRaw(0), readSoilRaw(1), readSoilRaw(2), t, h);
    delay(2000);
  }
}

void connectWiFi() {
  Serial.print("Connecting to WiFi");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected! IP: " + WiFi.localIP().toString());
}

// Accepts "ON" (default duration) or "ON:8" (8 seconds). Always capped at MAX_PUMP_RUN_MS.
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String message;
  for (unsigned int i = 0; i < length; i++) message += (char)payload[i];
  Serial.println("Message on [" + String(topic) + "]: " + message);

  if (String(topic) == TOPIC_COMMAND && message.startsWith("ON") && !pumpRunning) {
    unsigned long requestedMs = MAX_PUMP_RUN_MS;
    int colonIndex = message.indexOf(':');
    if (colonIndex != -1) {
      int seconds = message.substring(colonIndex + 1).toInt();
      if (seconds > 0) requestedMs = (unsigned long)seconds * 1000UL;
    }
    pumpRunDurationMs = min(requestedMs, MAX_PUMP_RUN_MS);
    Serial.printf("Pump ON for %lu ms\n", pumpRunDurationMs);
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
      mqttClient.publish(TOPIC_STATUS.c_str(), "idle");
    } else {
      Serial.printf("failed, rc=%d. Retrying in 3 seconds\n", mqttClient.state());
      delay(3000);
    }
  }
}

void setup() {
  pumpOff();                       // set the OFF level first...
  pinMode(RELAY_PIN, OUTPUT);      // ...then make the pin an output (pump stays OFF at boot)
  pumpOff();

  Serial.begin(115200);
  delay(500);
  for (int i = 0; i < 3; i++) {
    pinMode(SOIL_PWR_PINS[i], OUTPUT);
    digitalWrite(SOIL_PWR_PINS[i], LOW);
  }
  dht.begin();

  if (CALIBRATION_MODE) runCalibrationMode();   // never returns

  connectWiFi();
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setCallback(mqttCallback);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
  if (!mqttClient.connected()) connectMQTT();
  mqttClient.loop();

  // Safety cutoff: stop the pump when its time is up
  if (pumpRunning && (millis() - pumpStartTime >= pumpRunDurationMs)) {
    pumpOff();
    pumpRunning = false;
    Serial.println("Pump OFF (time is up).");
    mqttClient.publish(TOPIC_STATUS.c_str(), "idle");
  }

  if (millis() - lastReadTime >= READ_INTERVAL_MS) {
    lastReadTime = millis();

    int surface = readSoilPercent(0);
    int mid     = readSoilPercent(1);
    int root    = readSoilPercent(2);
    float temp = dht.readTemperature();
    float humidity = dht.readHumidity();

    Serial.printf("Soil surface:%d%% mid:%d%% root:%d%%  Temp:%.1fC  Humidity:%.1f%%\n",
                  surface, mid, root, temp, humidity);

    mqttClient.publish(TOPIC_SOIL_SURFACE.c_str(), String(surface).c_str());
    mqttClient.publish(TOPIC_SOIL_MID.c_str(),     String(mid).c_str());
    mqttClient.publish(TOPIC_SOIL_ROOT.c_str(),    String(root).c_str());
    if (!isnan(temp))     mqttClient.publish(TOPIC_TEMP.c_str(), String(temp).c_str());
    if (!isnan(humidity)) mqttClient.publish(TOPIC_HUMIDITY.c_str(), String(humidity).c_str());
  }
}
