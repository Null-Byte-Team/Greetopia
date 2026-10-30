/*
  ============================================================
  GREETOPIA - CAMERA NODE FIRMWARE v2 (AI-Thinker ESP32-CAM)
  ============================================================
  Based on the original CAM_Firmware (same camera setup, same POST /upload contract with the raw JPEG body and the
  X-Plant-Id header). Changes (see docs/FIRMWARE_CHANGES.md):
    * Sends X-Device-Token (the backend now REQUIRES it) and supports HTTPS with a pinned CA certificate.
    * Retries the upload (3 attempts, backoff) before sleeping, and only treats HTTP 2xx as success.
    * Refuses to run with the placeholder token/URL so a half-configured node never uploads in the clear.
    * Always returns after goToSleep() paths and checks that the frame is a JPEG before uploading.
  Photos are still periodic stills (every SLEEP_MINUTES), not video. The camera does not analyse images itself.
  SETUP: copy secrets.h.example -> secrets.h. Board: "AI Thinker ESP32-CAM". Not compiled on hardware by its author.
  ============================================================
*/

#include "esp_camera.h"
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include "secrets.h"

const uint64_t SLEEP_MINUTES = 30;
const unsigned long WIFI_TIMEOUT_MS = 20000;
const int UPLOAD_ATTEMPTS = 3;

// ---------- AI-THINKER ESP32-CAM PIN MAP (do not change) ----------
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

bool configIsPlaceholder() {
  return strcmp(DEVICE_TOKEN, "CHANGE_ME") == 0 || strlen(DEVICE_TOKEN) < 16 || strstr(SERVER_URL, "example.com") != nullptr;
}

// Returns the HTTP status code (or a negative HTTPClient error).
int uploadOnce(const uint8_t* data, size_t len) {
  HTTPClient http;
  WiFiClientSecure secure;
  bool begun;
#if USE_TLS
  secure.setCACert(SERVER_CA_CERT);
  begun = http.begin(secure, SERVER_URL);
#else
  begun = http.begin(SERVER_URL);
#endif
  if (!begun) return -1;
  http.setTimeout(15000);
  http.addHeader("Content-Type", "image/jpeg");
  http.addHeader("X-Plant-Id", PLANT_ID);
  http.addHeader("X-Device-Token", DEVICE_TOKEN);
  int code = http.POST((uint8_t*)data, len);
  http.end();
  return code;
}

void setup() {
  Serial.begin(115200);
  delay(500);

  if (configIsPlaceholder()) {
    Serial.println("secrets.h still has placeholder values (token/URL). Not uploading.");
    goToSleep();
    return;
  }
  if (!initCamera() || !connectWiFi()) {
    goToSleep();   // something failed: sleep and try again next cycle
    return;
  }

  // Throw away the first 2 frames: the camera needs a moment to adjust brightness
  for (int i = 0; i < 2; i++) {
    camera_fb_t* warm = esp_camera_fb_get();
    if (warm) esp_camera_fb_return(warm);
    delay(300);
  }

  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb || fb->len < 4 || fb->buf[0] != 0xFF || fb->buf[1] != 0xD8) {
    Serial.println("Photo capture failed or not a JPEG");
    if (fb) esp_camera_fb_return(fb);
    goToSleep();
    return;
  }
  Serial.printf("Photo taken: %u bytes\n", (unsigned)fb->len);

  bool delivered = false;
  for (int attempt = 1; attempt <= UPLOAD_ATTEMPTS && !delivered; attempt++) {
    int code = uploadOnce(fb->buf, fb->len);
    Serial.printf("Upload attempt %d -> %d\n", attempt, code);
    delivered = (code >= 200 && code < 300);   // the backend answers 201 (stored) or 201 "duplicate" for a retried capture
    if (!delivered && code >= 400 && code < 500) break;   // auth/validation errors will not fix themselves
    if (!delivered) delay(2000UL * attempt);
  }
  esp_camera_fb_return(fb);
  goToSleep();
}

void loop() {
  // never runs: the board sleeps at the end of setup()
}
