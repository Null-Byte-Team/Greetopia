/*
  ============================================================
  GREETOPIA - SENSOR NODE FIRMWARE v2 (ESP32 DevKit, 30-pin)
  ============================================================
  Based on the original Plant_Node_Firmware (same pins, same topics, same payload formats).
  Changes, all documented in docs/FIRMWARE_CHANGES.md:
    * The 15 s pump limit is enforced by a HARDWARE TIMER (esp_timer) that switches the relay off even if the
      main loop is blocked by Wi-Fi/MQTT. (Original: the cutoff sat behind blocking reconnect loops.)
    * No blocking while(){} reconnect loops; reconnect uses exponential backoff.
    * Strict command parsing ("ON" or "ON:<n>"), a running pump is never extended, minimum rest between runs and
      an hourly runtime budget (defence in depth), retained-message guard after (re)subscribing.
    * MQTT username/password + TLS, last-will "offline", retained "online" on plants/<id>/availability.
    * Optional acknowledgements on plants/<id>/ack and sensor faults on plants/<id>/fault. Old backends ignore them.
    * Shorted/open probes are reported as faults instead of being published as a (wrong) percentage.

  SETUP: copy secrets.h.example -> secrets.h and fill it in. Libraries: PubSubClient, DHT sensor library,
  Adafruit Unified Sensor. Board: "ESP32 Dev Module".
  HARDWARE: put a 10 k pull-up from the relay IN pin to 3.3 V (active-low modules) so the relay stays OFF while the
  ESP32 resets. This sketch has NOT been compiled on hardware by its author; follow docs/BENCH_TEST.md first.
  ============================================================
*/
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <DHT.h>
#include "esp_timer.h"
#include "pump_logic.h"
#include "secrets.h"

using namespace greetopia;

// ---------- MODE ----------
const bool CALIBRATION_MODE = true;   // true = print raw sensor numbers only (no Wi-Fi, pump OFF)

// ---------- PINS (unchanged from the original) ----------
#define DHT_PIN    4
#define RELAY_PIN  26
#define DHTTYPE    DHT22
const int SOIL_ADC_PINS[3] = {34, 35, 32};   // surface, mid, root
const int SOIL_PWR_PINS[3] = {25, 27, 14};   // each probe is powered only while it is read

// ---------- CALIBRATION (replace after running calibration mode) ----------
const int SOIL_DRY_VALUE[3] = {4095, 4095, 4095};
const int SOIL_WET_VALUE[3] = {1500, 1500, 1500};

// ---------- SETTINGS ----------
const bool RELAY_ACTIVE_LOW = true;
const unsigned long READ_INTERVAL_MS = 10000;
const unsigned long FAULT_REPORT_INTERVAL_MS = 60000;
const unsigned long WIFI_RETRY_MS = 5000;
const unsigned long MQTT_BACKOFF_MIN_MS = 2000;
const unsigned long MQTT_BACKOFF_MAX_MS = 60000;

// ---------- topics (identical to the original, plus availability/ack/fault) ----------
String P = String("plants/") + PLANT_ID + "/";
String T_SURFACE = P + "soil/surface", T_MID = P + "soil/mid", T_ROOT = P + "soil/root";
String T_TEMP = P + "temp", T_HUM = P + "humidity", T_STATUS = P + "status", T_CMD = P + "water";
String T_AVAIL = P + "availability", T_ACK = P + "ack", T_FAULT = P + "fault";
const char* SOIL_NAMES[3] = {"soil_surface", "soil_mid", "soil_root"};

#if USE_TLS
WiFiClientSecure netClient;
#else
WiFiClient netClient;
#endif
PubSubClient mqttClient(netClient);
DHT dht(DHT_PIN, DHTTYPE);
PumpController pump;

esp_timer_handle_t pumpTimer = nullptr;
volatile bool pumpTimedOut = false;          // set from the timer task, handled in loop()
unsigned long lastReadTime = 0, lastWifiTry = 0, lastMqttTry = 0, mqttBackoff = MQTT_BACKOFF_MIN_MS;
unsigned long lastFaultReport[3] = {0, 0, 0};

void pumpOn()  { digitalWrite(RELAY_PIN, RELAY_ACTIVE_LOW ? LOW  : HIGH); }
void pumpOff() { digitalWrite(RELAY_PIN, RELAY_ACTIVE_LOW ? HIGH : LOW);  }

// Runs in the esp_timer task, independent of loop(): the pump stops on time even while Wi-Fi/MQTT block.
void onPumpTimer(void*) {
  pumpOff();
  pumpTimedOut = true;
}

void startPumpTimer(uint32_t durationMs) {
  esp_timer_stop(pumpTimer);   // harmless if not running
  esp_timer_start_once(pumpTimer, (uint64_t)durationMs * 1000ULL);
}

int readSoilRaw(int i) {
  digitalWrite(SOIL_PWR_PINS[i], HIGH);
  delay(100);
  long total = 0;
  for (int n = 0; n < 16; n++) { total += analogRead(SOIL_ADC_PINS[i]); delay(2); }
  digitalWrite(SOIL_PWR_PINS[i], LOW);
  return (int)(total / 16);
}

void runCalibrationMode() {
  Serial.println("\n=== CALIBRATION MODE (no Wi-Fi, pump OFF) ===");
  while (true) {
    Serial.printf("RAW  surface=%4d  mid=%4d  root=%4d   |  temp=%.1f C  humidity=%.1f %%\n",
                  readSoilRaw(0), readSoilRaw(1), readSoilRaw(2), dht.readTemperature(), dht.readHumidity());
    delay(2000);
  }
}

void publishText(const String& topic, const char* text, bool retained = false) {
  if (mqttClient.connected()) mqttClient.publish(topic.c_str(), text, retained);
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  if (String(topic) != T_CMD) return;
  uint32_t durationMs = 0;
  CmdStatus s = pump.request(millis(), (const char*)payload, length, &durationMs);
  switch (s) {
    case CmdStatus::Accepted: {
      pumpTimedOut = false;
      startPumpTimer(durationMs);    // hardware cutoff first ...
      pumpOn();                      // ... then switch the pump on
      Serial.printf("Pump ON for %lu ms\n", (unsigned long)durationMs);
      char ack[20]; snprintf(ack, sizeof(ack), "accepted:%lu", (unsigned long)(durationMs / 1000));
      publishText(T_ACK, ack);
      publishText(T_STATUS, "watering");
      break;
    }
    case CmdStatus::Invalid:  publishText(T_ACK, "rejected:invalid"); break;
    case CmdStatus::Busy:     publishText(T_ACK, "rejected:busy");    break;
    case CmdStatus::Rest:     publishText(T_ACK, "rejected:rest");    break;
    case CmdStatus::Budget:   publishText(T_ACK, "rejected:budget");  break;
    case CmdStatus::TooEarly: break;   // possible retained leftover: ignore silently
  }
}

// Non-blocking: one short step per call.
void serviceWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  if (millis() - lastWifiTry < WIFI_RETRY_MS && lastWifiTry != 0) return;
  lastWifiTry = millis();
  Serial.println("Wi-Fi (re)connecting...");
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void serviceMqtt() {
  if (WiFi.status() != WL_CONNECTED || mqttClient.connected()) return;
  if (millis() - lastMqttTry < mqttBackoff && lastMqttTry != 0) return;
  lastMqttTry = millis();
  String clientId = String("greetopia-") + PLANT_ID;
  bool ok = mqttClient.connect(clientId.c_str(), MQTT_USER, MQTT_PASS, T_AVAIL.c_str(), 1, true, "offline");
  if (!ok) {
    Serial.printf("MQTT connect failed rc=%d, retry in %lu ms\n", mqttClient.state(), mqttBackoff);
    mqttBackoff = min(mqttBackoff * 2, MQTT_BACKOFF_MAX_MS);
    return;
  }
  mqttBackoff = MQTT_BACKOFF_MIN_MS;
  mqttClient.subscribe(T_CMD.c_str());
  pump.onSubscribed(millis());                           // ignore commands in the first moments (retained leftovers)
  mqttClient.publish(T_AVAIL.c_str(), "online", true);
  publishText(T_STATUS, pump.running ? "watering" : "idle");
  Serial.println("MQTT connected");
}

void readAndPublish() {
  char buf[16];
  int values[3];
  for (int i = 0; i < 3; i++) {
    int raw = readSoilRaw(i);
    SoilState st = classifySoil(raw, SOIL_DRY_VALUE[i], SOIL_WET_VALUE[i]);
    if (st != SoilState::Ok) {   // never publish a percentage computed from an implausible raw value
      values[i] = -1;
      if (millis() - lastFaultReport[i] >= FAULT_REPORT_INTERVAL_MS || lastFaultReport[i] == 0) {
        lastFaultReport[i] = millis();
        String msg = String(SOIL_NAMES[i]) + ":" + (st == SoilState::Shorted ? "shorted" : "open");
        publishText(T_FAULT, msg.c_str());
      }
      continue;
    }
    values[i] = soilPercent(raw, SOIL_DRY_VALUE[i], SOIL_WET_VALUE[i]);
  }
  float temp = dht.readTemperature(), humidity = dht.readHumidity();
  Serial.printf("Soil %d/%d/%d  Temp %.1f  Hum %.1f\n", values[0], values[1], values[2], temp, humidity);
  const String* topics[3] = {&T_SURFACE, &T_MID, &T_ROOT};
  for (int i = 0; i < 3; i++) if (values[i] >= 0) { snprintf(buf, sizeof(buf), "%d", values[i]); publishText(*topics[i], buf); }
  if (!isnan(temp))     { dtostrf(temp, 1, 2, buf);     publishText(T_TEMP, buf); }
  if (!isnan(humidity)) { dtostrf(humidity, 1, 2, buf); publishText(T_HUM, buf); }
}

void setup() {
  pumpOff();
  pinMode(RELAY_PIN, OUTPUT);
  pumpOff();
  Serial.begin(115200);
  delay(500);
  for (int i = 0; i < 3; i++) { pinMode(SOIL_PWR_PINS[i], OUTPUT); digitalWrite(SOIL_PWR_PINS[i], LOW); }
  dht.begin();
  if (CALIBRATION_MODE) runCalibrationMode();   // never returns

  esp_timer_create_args_t args = {};
  args.callback = &onPumpTimer;
  args.name = "pump_off";
  esp_timer_create(&args, &pumpTimer);

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
#if USE_TLS
  netClient.setCACert(MQTT_CA_CERT);
#endif
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setCallback(mqttCallback);
}

void loop() {
  serviceWifi();
  serviceMqtt();
  mqttClient.loop();

  // Software cutoff as a second layer; the hardware timer normally fires first.
  if (pump.running && (pumpTimedOut || pump.shouldStop(millis()))) {
    pumpOff();
    esp_timer_stop(pumpTimer);
    pump.stopped(millis());
    pumpTimedOut = false;
    Serial.println("Pump OFF");
    publishText(T_STATUS, "idle");
  }

  if (millis() - lastReadTime >= READ_INTERVAL_MS) {
    lastReadTime = millis();
    readAndPublish();
  }
}
