# Greetopia 🌱 — AI-Powered Smart Irrigation & Plant Care System

[![Backend](https://img.shields.io/badge/Backend-FastAPI%20%7C%20Python%203.12-blue?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![Frontend](https://img.shields.io/badge/Frontend-React%2018%20%7C%20Vite%20%7C%20TypeScript-61dafb?style=flat-square&logo=react)](https://vitejs.dev)
[![AI Engine](https://img.shields.io/badge/AI-Google%20Gemini-orange?style=flat-square&logo=google)](https://ai.google.dev)
[![Hardware](https://img.shields.io/badge/Hardware-ESP32%20%2B%20ESP32--CAM-red?style=flat-square&logo=espressif)](https://www.espressif.com)
[![Tests](https://img.shields.io/badge/Backend%20Tests-105%20Passing-success?style=flat-square&logo=pytest)](https://pytest.org)

**Greetopia** is a full-stack, AI-grounded smart irrigation and plant telemetry platform. It connects physical ESP32 sensor and camera nodes to an interactive real-time dashboard powered by **FastAPI**, **React**, **SQLite**, and **Google Gemini AI**.

📖 **Hardware Setup Guide:** [`ESP32_SETUP_GUIDE.md`](ESP32_SETUP_GUIDE.md)

---

## 📑 Table of Contents

- [System Architecture](#system-architecture)
- [Key Features](#key-features)
- [Hardware & Pin Setup](#hardware--pin-setup)
- [Firmware Reference](#firmware-reference)
- [API Reference](#api-reference)
- [Local Quick Start](#local-quick-start)
- [Deployment on Vercel](#deployment-on-vercel)
- [Environment Variables](#environment-variables)
- [Safety & Fail-Safe Architecture](#safety--fail-safe-architecture)

---

## System Architecture

```mermaid
graph TD
    subgraph Hardware ["Hardware Layer (ESP32)"]
        Sensors["Soil Sensors (3 Depths)<br/>+ DHT22 Temp & Humidity"] --> |HTTP POST / MQTT| ESP32["ESP32 Sensor Node"]
        Camera["AI-Thinker ESP32-CAM"] --> |HTTP POST JPEG| CAM["Camera Node"]
        Relay["5V Relay + Pump"] <--- |GPIO 26 Cutoff| ESP32
    end

    subgraph Backend ["Backend Layer (FastAPI, one long-running container)"]
        API["FastAPI API (/api/v1)"]
        DB[(SQLite on a persistent disk)]
        VPD["VPD & Analytics Engine"]
        Engine["Deterministic Decision Engine"]
        AI["Gemini Assistant (optional)"]
        
        ESP32 -->|POST /telemetry| API
        CAM -->|POST /upload| API
        API --> DB
        API --> VPD
        API --> Engine
        API --> AI
    end

    subgraph Frontend ["Frontend Layer (React 18 + Vite)"]
        UI["Web Dashboard / PWA"]
        Charts["Recharts Trend Analytics"]
        Chat["Plant Knowledge AI Chatbot"]
        
        UI <-->|JSON REST API| API
    end
```

---

## Key Features

- **3-Depth Soil Telemetry:** Reads soil-moisture probes (see firmware header for the probe type) at surface (~2–3cm), mid-depth (~7–8cm), and root zone (~15cm) to observe moisture infiltration dynamics.
- **Microclimate & VPD Engine:** Ingests DHT22 air temperature and humidity to compute live Vapor Pressure Deficit (VPD) in kPa with stress-band classification (*under-transpiration*, *healthy*, *high stress*).
- **Dual IoT Telemetry Ingestion:**
  - **Direct HTTP REST API (`POST /api/v1/plants/{id}/telemetry`):** Native HTTPS posting straight to Vercel without third-party broker dependencies.
  - **Authenticated MQTT Subscriber (`paho-mqtt`):** Full username/password and TLS support for persistent broker environments (e.g., HiveMQ, EMQX, Mosquitto).
- **Grounded Gemini AI Assistant (model set by `GEMINI_MODEL`):** Conversational care assistant grounded in live sensor history, species care profiles, VPD, and recent watering events with automatic multi-model fallback.
- **Offline Plant Knowledge Base:** Bundled catalog of 36 curated plant profiles seeded into SQLite with fast full-text search.
- **Fail-Safe Protection:** firmware v2 stops the pump with a hardware timer (max 15 s), the backend enforces cooldown, daily caps, pending-command and sensor-sanity checks, and every command is recorded as *requested* until telemetry confirms it.
- **Accounts & roles:** every data/control endpoint needs a signed-in user; the first account is admin, later accounts are read-only until promoted.

---

## Hardware & Pin Setup

For a full step-by-step wiring guide, see [`ESP32_SETUP_GUIDE.md`](ESP32_SETUP_GUIDE.md).

| Component | Sensor Pin | ESP32 Pin | Purpose |
| :--- | :--- | :--- | :--- |
| **Surface Soil Sensor** | Analog Out | **GPIO 34** | Surface moisture (ADC1) |
| **Mid-Depth Soil Sensor** | Analog Out | **GPIO 35** | Mid root moisture (ADC1) |
| **Root-Zone Soil Sensor** | Analog Out | **GPIO 32** | Primary irrigation trigger (ADC1) |
| **DHT22** | Data Out | **GPIO 4** | Ambient temperature & relative humidity |
| **Relay Module** | Signal (IN) | **GPIO 26** | Submersible pump control (Active LOW) |
| **ESP32-CAM** | Camera Lens | Standalone Node | Periodic JPEG plant captures |

---

## Firmware

| Folder | What it is |
| :--- | :--- |
| [`firmware/sensor_node/`](firmware/sensor_node/) | **v2 sensor + pump node** (hardware-timer pump cutoff, non-blocking reconnect, MQTT auth/TLS, availability, acks, fault reports). Logic is unit-tested on a PC. |
| [`firmware/camera_node/`](firmware/camera_node/) | **v2 camera node** (device token, HTTPS, retries). Same `POST /upload` + `X-Plant-Id` contract. |
| [`firmware_reference/`](firmware_reference/) | Original sketches, unmodified, for reference. |

v2 has **not been compiled or run on hardware by its author**. Follow [`docs/BENCH_TEST.md`](docs/BENCH_TEST.md) (pump disconnected) before connecting a pump.
Details of every change: [`docs/FIRMWARE_CHANGES.md`](docs/FIRMWARE_CHANGES.md). Contract: [`docs/firmware_contract.md`](docs/firmware_contract.md).

---

## API Reference

The FastAPI backend exposes interactive OpenAPI docs at `/docs`.

### Core Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/health` | Minimal public status (details for admins at `/api/v1/health/details`) |
| `GET` | `/health/ready` | Readiness probe reporting database and MQTT status |
| `GET` | `/api/v1/plants` | List all tracked plants |
| `GET` | `/api/v1/plants/{id}/overview` | Complete plant snapshot: live readings, VPD, weather, analytics |
| `POST` | `/api/v1/plants/{id}/telemetry` | Ingest sensor readings directly via JSON HTTP POST |
| `POST` | `/api/v1/plants/{id}/water` | Manual pump run, 1–15 s, operator role; refused during cooldown / pending command / daily cap (409/429) |
| `POST` | `/api/v1/plants/{id}/decision` | Run deterministic irrigation check |
| `POST` | `/api/v1/plants/{id}/chat` | Ask Gemini about plant condition with grounded telemetry |
| `POST` | `/upload` | ESP32-CAM raw JPEG photo upload |
| `GET` | `/api/v1/plant-knowledge?q=tomato` | Search local offline-first plant database |

#### Example: Submitting Sensor Telemetry via HTTP

```http
POST /api/v1/plants/plant01/telemetry
Content-Type: application/json
X-Device-Token: <DEVICE_UPLOAD_TOKEN>

{
  "soil_surface": 42.0,
  "soil_mid": 48.5,
  "soil_root": 35.0,
  "temperature_c": 25.1,
  "humidity_pct": 62.0
}
```

---

## Local Quick Start

### Prerequisites
- **Python 3.11+**
- **Node.js 20+** & npm

### 1. Backend Setup
```bash
cd backend
python -m venv .venv

# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 5000
```

### 2. Frontend Setup
In a second terminal:
```bash
cd frontend
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173). The Vite dev server automatically proxies `/api` calls to `http://localhost:5000`.

---

## Deployment

The backend is **one long-running process** (MQTT consumer + decision scheduler + SQLite on a persistent disk). Serverless platforms
(Vercel Functions, Lambda) are not supported: they cannot hold an MQTT connection and lose the database.

- **Backend:** Render (see `render.yaml`) or `docker compose up` with a persistent volume. Production requires `JWT_SECRET` and `DEVICE_UPLOAD_TOKEN`.
- **Frontend:** Vercel (static build, see `vercel.json`) or the nginx image in `docker-compose.yml`. Set `VITE_API_BASE=https://<backend>/api/v1` at build time.
- **MQTT:** use a private broker with an ACL (`deploy/mosquitto/`). Public brokers are refused unless `MQTT_DEV_PUBLIC_BROKER=true`.
- **Mobile:** rebuild the Android app after setting `VITE_API_BASE` (the previously committed APK pointed to the old serverless URL and must not be reused).

---

## Environment Variables

Copy `backend/.env.example` to `backend/.env` (never commit or archive it; it holds secrets). See the file for every option:

```env
# Application
APP_NAME=Greetopia API
API_PREFIX=/api/v1
CORS_ORIGINS=http://localhost:5173,capacitor://localhost   # explicit origins only

# MQTT Broker (Optional for Persistent Container Hosting)
MQTT_ENABLED=false
MQTT_HOST=127.0.0.1
MQTT_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=
MQTT_TLS=false

# Google Gemini AI
GEMINI_ENABLED=true
GEMINI_MODEL=gemini-2.5-flash
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_CHAT_API_KEY=

# Safety & Irrigation Engine
AUTO_DECISIONS_ENABLED=false
DECISION_INTERVAL_MINUTES=15
IRRIGATION_COOLDOWN_MINUTES=30
ROOT_MOISTURE_THRESHOLD=28
DEFAULT_WATER_SECONDS=5

# Security (required in production)
JWT_SECRET=<python -c "import secrets; print(secrets.token_urlsafe(48))">
DEVICE_UPLOAD_TOKEN=<shared secret for ESP32 nodes>
ADMIN_EMAILS=you@example.com
```

---

## Safety & Fail-Safe Architecture

Greetopia enforces multi-layer safety controls to prevent accidental overwatering:

1. **Hardware Cutoff:** Firmware code clamps maximum pump activation to **15 seconds**, turning the relay OFF even if network or server communication drops.
2. **API Clamping:** Manual water requests are strictly validated to `1..15` seconds by Pydantic schemas.
3. **Irrigation Cooldown:** A 30-minute mandatory cooldown window prevents repeated watering cycles before water has soaked to the root zone.
4. **Sensor Freshness Safeguard:** The automatic decision engine refuses to trigger pump commands if telemetry readings are older than 5 minutes.
5. **Rain Skip Logic:** Integrated weather forecasts skip scheduled irrigations if rain probability exceeds the configured threshold.

---

## Automated Test Suite

Run backend test verification (includes API routes, VPD, decision engine, and telemetry ingestion):

```bash
cd backend
python -m pytest tests/ -v
```
*(105 backend tests; firmware logic: `g++ -std=c++17 firmware/sensor_node/tests/test_pump_logic.cpp`).*

---

## License

This project is open-source under the MIT License.
