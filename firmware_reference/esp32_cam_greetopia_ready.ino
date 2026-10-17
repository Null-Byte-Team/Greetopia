/*
  ============================================================
  SMART IRRIGATION - CAMERA NODE FIRMWARE (AI-Thinker ESP32-CAM)
  ============================================================
  What it does, in plain words:
    1. Wakes up every SLEEP_MINUTES minutes.
    2. Joins your WiFi.
    3. Takes a photo of the plant.
    4. Sends the photo to your server (a small Python program on
       your laptop/cloud) using a normal web POST.
    5. Goes back to deep sleep (uses almost no power).

  ARDUINO IDE SETTINGS:
    - Board: "AI Thinker ESP32-CAM"
    - No extra libraries needed (camera + WiFi + HTTPClient come
      with the ESP32 board package)

  HOW TO UPLOAD (ESP32-CAM has no USB port of its own):
    Use the ESP32-CAM-MB USB base: plug the camera into it,
    plug USB into laptop, press Upload.

  IF YOU SEE A COMPILE ERROR about "pin_sccb_sda":
    change the two "sccb" words to "sscb" (older board package).
  ============================================================
*/

#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>

// ---------- 1. FILL THESE IN ----------
const char* WIFI_SSID     = "YOUR_WIFI_NAME";      // must be 2.4GHz
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* SERVER_URL    = "http://192.168.1.50:5000/upload"; // your laptop's IP + port
const char* PLANT_ID      = "plant01";              // must match the sensor node's PLANT_ID
const char* DEVICE_UPLOAD_TOKEN = "";               // optional; must match backend DEVICE_UPLOAD_TOKEN

// ---------- 2. SETTINGS ----------
const uint64_t SLEEP_MINUTES = 30;        // photo every 30 minutes
const unsigned long WIFI_TIMEOUT_MS = 20000;

// ---------- 3. AI-THINKER ESP32-CAM PIN MAP (do not change) ----------
#define PWDN_GPIO_NUM   32
#define RESET_GPIO_NUM  -1
#define XCLK_GPIO_NUM    0
#define SIOD_GPIO_NUM   26
#define SIOC_GPIO_NUM   27
#define Y9_GPIO_NUM     35
#define Y8_GPIO_NUM     34
#define Y7_GPIO_NUM     39
#define Y6_GPIO_NUM     36
#define Y5_GPIO_NUM     21
#define Y4_GPIO_NUM     19
#define Y3_GPIO_NUM     18
#define Y2_GPIO_NUM      5
#define VSYNC_GPIO_NUM  25
#define HREF_GPIO_NUM   23
#define PCLK_GPIO_NUM   22

bool initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk  = XCLK_GPIO_NUM;
  config.pin_pclk  = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href  = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn  = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size   = FRAMESIZE_SVGA;   // 800x600: sharp enough for leaf details, small upload
  config.jpeg_quality = 12;               // 10 = best quality, 63 = worst
  config.fb_count     = 1;
  config.fb_location  = CAMERA_FB_IN_PSRAM;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    return false;
  }
  return true;
}

bool connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - start > WIFI_TIMEOUT_MS) return false;
    delay(300);
  }
  Serial.println("WiFi connected: " + WiFi.localIP().toString());
  return true;
}

void goToSleep() {
  Serial.println("Going to sleep...");
  esp_sleep_enable_timer_wakeup(SLEEP_MINUTES * 60ULL * 1000000ULL);
  esp_deep_sleep_start();
}

void setup() {
  Serial.begin(115200);
  delay(500);

  if (!initCamera() || !connectWiFi()) {
    goToSleep();   // something failed: sleep and try again next cycle
  }

  // Throw away the first 2 frames: the camera needs a moment to adjust brightness
  for (int i = 0; i < 2; i++) {
    camera_fb_t* warm = esp_camera_fb_get();
    if (warm) esp_camera_fb_return(warm);
    delay(300);
  }

  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Photo capture failed");
    goToSleep();
  }
  Serial.printf("Photo taken: %u bytes\n", fb->len);

  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "image/jpeg");
  http.addHeader("X-Plant-Id", PLANT_ID);
  if (DEVICE_UPLOAD_TOKEN[0] != '\0') {
    http.addHeader("X-Device-Token", DEVICE_UPLOAD_TOKEN);
  }
  int code = http.POST(fb->buf, fb->len);
  if (code >= 200 && code < 300) {
    Serial.printf("Photo upload succeeded: HTTP %d\n", code);
  } else {
    Serial.printf("Photo upload failed: HTTP %d\n", code);
  }
  http.end();

  esp_camera_fb_return(fb);
  goToSleep();
}

void loop() {
  // never runs: the board sleeps at the end of setup()
}
