# Greetopia ESP32 Hardware & Sensor Setup Guide

This guide explains how to connect your physical sensors to the ESP32, configure the firmware, and stream live readings to your Greetopia dashboard at **[https://greetopia.vercel.app](https://greetopia.vercel.app)**.

---

## 1. Required Hardware

- **ESP32 Development Board** (NodeMCU-32S, ESP32-WROOM-32, or similar)
- **Capacitive Soil Moisture Sensors (v1.2 or v2.0)**:
  - Surface depth (~2–3 cm)
  - Mid depth (~7–8 cm)
  - Root zone depth (~15 cm, primary signal)
- **DHT22 Temperature & Humidity Sensor** (or AM2302)
- **5V 1-Channel Relay Module** (for the 5V/12V submersible water pump)
- **Submersible 5V/12V Mini Water Pump + Tubing**
- **Breadboard & Jumper Wires**
- **USB Cable** to connect the ESP32 to your computer

---

## 2. Wiring & Pinout Table

> [!IMPORTANT]
> The ESP32 analog-to-digital converter (ADC1) pins `GPIO 32, 34, 35` are used for the analog soil sensors. Do **not** use ADC2 pins (GPIO 0, 2, 4, 12-15, 25-27) for analog inputs if WiFi is enabled.

| Component | Sensor Pin | ESP32 Pin | Notes |
| :--- | :--- | :--- | :--- |
| **Surface Soil Sensor** | VCC | 3.3V | Powered by 3.3V rail |
| | GND | GND | Ground |
| | AOUT (Analog) | **GPIO 34** | ADC1 input |
| **Mid-Depth Soil Sensor** | VCC | 3.3V | Powered by 3.3V rail |
| | GND | GND | Ground |
| | AOUT (Analog) | **GPIO 35** | ADC1 input |
| **Root-Zone Soil Sensor** | VCC | 3.3V | Powered by 3.3V rail |
| | GND | GND | Ground |
| | AOUT (Analog) | **GPIO 32** | ADC1 input (Primary signal) |
| **DHT22 (Temp & Hum)** | VCC | 3.3V or 5V | Depending on module type |
| | GND | GND | Ground |
| | DATA | **GPIO 4** | Digital I/O |
| **Relay Module (Pump)** | VCC | 5V (VIN) | Relay coils need 5V |
| | GND | GND | Shared common ground |
| | IN (Signal) | **GPIO 26** | Digital Output (Active LOW) |

---

## 3. Arduino IDE Setup

1. **Install ESP32 Board Support:**
   - Go to **File → Preferences**.
   - Add this URL to *Additional Boards Manager URLs*:
     ```text
     https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
     ```
   - Go to **Tools → Board → Boards Manager**, search for `esp32`, and install it.

2. **Install Required Libraries:**
   Go to **Tools → Manage Libraries** and install:
   - **`PubSubClient`** by Nick O'Leary *(for MQTT support)*
   - **`DHT sensor library`** by Adafruit *(for temperature and humidity)*
   - **`Adafruit Unified Sensor`** by Adafruit *(dependency for DHT)*

---

## 4. Firmware Configuration

Open the ready-to-use sketch file in Arduino IDE:
👉 **[`firmware/sensor_node/`](firmware/sensor_node/) (v2; copy `secrets.h.example` to `secrets.h` first)**

### Step 4.1: Enter Your WiFi Credentials
```cpp
const char* WIFI_SSID     = "YOUR_WIFI_NAME";     // Must be 2.4 GHz WiFi
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
```

### Step 4.2: Choose Your Communication Mode

#### Option A: Direct HTTP to Vercel (Recommended — Easiest)
This sends data directly to your live Vercel cloud deployment without needing an external MQTT broker:
```cpp
const bool  USE_HTTP     = true;
const bool  USE_MQTT     = false;
const char* HTTP_API_URL = "https://greetopia.vercel.app/api/v1/plants/plant01/telemetry";
const char* DEVICE_TOKEN = ""; // Leave blank or match DEVICE_UPLOAD_TOKEN from backend .env
```

#### Option B: Authenticated MQTT Broker (HiveMQ, EMQX, Mosquitto)
If you run an always-on backend instance (e.g. Render, Railway, or local Docker) and have an MQTT broker:
```cpp
const bool  USE_HTTP      = false;
const bool  USE_MQTT      = true;
const char* MQTT_BROKER   = "your-broker-domain.hivemq.cloud";
const int   MQTT_PORT     = 1883; // or 8883 for TLS
const char* MQTT_USERNAME = "your_mqtt_username";
const char* MQTT_PASSWORD = "your_mqtt_password";
```

---

## 5. Uploading the Firmware

1. Plug your ESP32 board into your computer with a USB data cable.
2. Under **Tools → Board**, select **DOIT ESP32 DEVKIT V1** (or your specific ESP32 board).
3. Under **Tools → Port**, select the COM port of your ESP32 (e.g., `COM3`, `COM4`).
4. Click the **Upload** button (arrow icon).
5. If the IDE shows `Connecting........_____.....`, press and hold the **BOOT** button on the ESP32 until the upload starts.

---

## 6. What to Expect in Serial Monitor

Open the Arduino IDE **Serial Monitor** at **115200 baud**:

```text
Connecting to WiFi: MyHomeWiFi
.....
WiFi connected! IP address: 192.168.1.105
Readings -> Surface: 45% | Mid: 52% | Root: 38% | Temp: 24.5C | Hum: 58.0%
HTTP telemetry sent, response code: 201
```

A response code of **`201`** means the Vercel backend received and stored the data successfully!

---

## 7. Verifying on the Dashboard

Once the ESP32 sends its first packet:
1. Open **[https://greetopia.vercel.app](https://greetopia.vercel.app)** in your browser.
2. The indicator badge changes to **`RECEIVING TELEMETRY`**.
3. **Live Cards:**
   - **Root-zone soil:** shows your plant's active moisture percentage.
   - **Air temperature & Humidity:** shows live room conditions from DHT22.
   - **VPD Index:** calculated live (in kPa) to indicate transpiration stress.
4. **Soil Moisture Trends Chart:** plots data points every 10 seconds.
5. **Gemini Plant Assistant:** incorporates live soil and climate conditions when you ask questions.

---

## 8. Calibrating the Capacitive Soil Sensors

Every soil moisture probe (the original firmware comments describe cheap resistive probes; capacitive probes also work) has slight hardware variations. To calibrate yours for maximum precision:

1. **Dry Air Reading (0% Moisture):**
   - Hold the sensor in the air.
   - Check the raw reading in the Serial Monitor (e.g., `3000` or `3200`).
   - Update `SOIL_DRY_VALUE` in the sketch:
     ```cpp
     const int SOIL_DRY_VALUE = 3000;
     ```

2. **Wet / Submerged Reading (100% Moisture):**
   - Dip the sensor into a cup of water up to the white guideline (do not submerge the electronics at the top).
   - Check the raw value in the Serial Monitor (e.g., `1200` or `1400`).
   - Update `SOIL_WET_VALUE` in the sketch:
     ```cpp
     const int SOIL_WET_VALUE = 1200;
     ```

3. Re-upload the sketch to the ESP32.

---

## 9. Troubleshooting FAQ

- **WiFi does not connect:**
  - The ESP32 only supports **2.4 GHz WiFi**. Ensure your router has 2.4 GHz enabled and the SSID/Password are exact.
- **DHT22 reads `0.0` or `NaN`:**
  - Verify the data pin is connected to `GPIO 4`.
  - Check whether your DHT module has a built-in pullup resistor. If using a bare 4-pin DHT22, place a 10kΩ resistor between VCC and DATA.
- **Relay clicks ON immediately on boot:**
  - Most relay modules are "active LOW". If yours turns ON when it shouldn't, verify `const bool RELAY_ACTIVE_LOW = true;` in the sketch.
- **Dashboard shows "Waiting for sensor data":**
  - Greetopia marks data as stale after 5 minutes without a new reading (`SENSOR_STALE_MINUTES = 5`). Ensure the ESP32 is powered on and sending data every 10 seconds.


---
> **Safety update:** use firmware v2 (`firmware/sensor_node`, `firmware/camera_node`) and a **private MQTT broker** (`deploy/mosquitto/`).
> Add a 10 k pull-up from the relay IN pin to 3.3 V so the relay stays OFF while the ESP32 resets, and run `docs/BENCH_TEST.md` with the pump disconnected first.
