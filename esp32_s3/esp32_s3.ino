#include <WiFi.h>
#include <HTTPClient.h>
#include <ESP_I2S.h>
#include "esp_camera.h"

#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEServer.h>

// =======================
// Wi-Fi settings
// =======================
const char* ssid = "your wifi";
const char* password = "your password";
const char* pcBaseUrl = "http://192.168.1.235:8000";

// =======================
// BLE settings
// =======================
#define SERVICE_UUID        "12345678-1234-1234-1234-1234567890ab"
#define CHARACTERISTIC_UUID "abcd1234-5678-1234-5678-abcdef123456"

BLEAdvertising *advertising;

// =======================
// Camera pins for XIAO ESP32-S3 Sense
// =======================
#define PWDN_GPIO_NUM     -1
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM     10
#define SIOD_GPIO_NUM     40
#define SIOC_GPIO_NUM     39

#define Y9_GPIO_NUM       48
#define Y8_GPIO_NUM       11
#define Y7_GPIO_NUM       12
#define Y6_GPIO_NUM       14
#define Y5_GPIO_NUM       16
#define Y4_GPIO_NUM       18
#define Y3_GPIO_NUM       17
#define Y2_GPIO_NUM       15

#define VSYNC_GPIO_NUM    38
#define HREF_GPIO_NUM     47
#define PCLK_GPIO_NUM     13

// =======================
// Microphone pins
// =======================
#define MIC_CLK_PIN  42
#define MIC_DATA_PIN 41

I2SClass I2S;

// =======================
// Audio settings
// =======================
const int SAMPLE_RATE = 16000;
const int BITS_PER_SAMPLE = 16;
const int CHANNELS = 1;
const int RECORD_SECONDS = 3;

const int RAW_TRIGGER_THRESHOLD = 3000;
const int LOUDNESS_TRIGGER_THRESHOLD = 700;
const int AUDIO_COOLDOWN_MS = 5000;

unsigned long lastAudioTriggerTime = 0;

// =======================
// Runtime flags
// =======================
volatile bool grabRequested = false;
bool busyCamera = false;
bool busyAudio = false;

// =======================
// Wi-Fi
// =======================
bool connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }

  Serial.print("Connecting to Wi-Fi: ");
  Serial.println(ssid);

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);

  WiFi.disconnect(true);
  delay(500);

  WiFi.begin(ssid, password);

  unsigned long startTime = millis();

  while (WiFi.status() != WL_CONNECTED && millis() - startTime < 20000) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("Wi-Fi connected.");
    Serial.print("ESP32 IP: ");
    Serial.println(WiFi.localIP());
    return true;
  } else {
    Serial.print("Wi-Fi failed. Status = ");
    Serial.println(WiFi.status());
    return false;
  }
}

// =======================
// Upload helper
// =======================
bool httpPostBytes(const char* endpoint, const char* contentType, uint8_t* data, size_t len) {
  if (!connectWiFi()) {
    Serial.println("Upload cancelled: Wi-Fi unavailable.");
    return false;
  }

  String url = String(pcBaseUrl) + endpoint;

  HTTPClient http;
  http.begin(url);
  http.addHeader("Content-Type", contentType);

  Serial.print("Uploading to: ");
  Serial.println(url);

  int code = http.POST(data, len);

  Serial.print("HTTP response code: ");
  Serial.println(code);

  String response = http.getString();
  Serial.print("Server response: ");
  Serial.println(response);

  http.end();

  return code == 200;
}

// =======================
// Camera init
// =======================
bool initCamera() {
  camera_config_t config;
  memset(&config, 0, sizeof(config));

  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;

  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;

  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;

  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;

  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;

  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  config.frame_size   = FRAMESIZE_QVGA;
  config.jpeg_quality = 12;

  config.fb_count     = 1;

  if (psramFound()) {
    Serial.println("PSRAM found for camera.");
    config.fb_location = CAMERA_FB_IN_PSRAM;
  } else {
    Serial.println("PSRAM not found. Camera using DRAM.");
    config.fb_location = CAMERA_FB_IN_DRAM;
  }

  config.grab_mode = CAMERA_GRAB_LATEST;

  esp_err_t err = esp_camera_init(&config);

  if (err != ESP_OK) {
    Serial.print("Camera init failed. Error: 0x");
    Serial.println(err, HEX);
    return false;
  }

  Serial.println("Camera initialized.");
  return true;
}

// =======================
// Capture 3 fresh photos first, then upload
// =======================
void captureThreePhotos() {
  if (busyCamera) {
    Serial.println("Camera busy. Ignoring GRAB.");
    return;
  }

  busyCamera = true;

  Serial.println("GRAB received. Capturing 3 fresh photos first, then uploading.");

  const int NUM_PHOTOS = 3;
  uint8_t* photoData[NUM_PHOTOS] = {nullptr, nullptr, nullptr};
  size_t photoLen[NUM_PHOTOS] = {0, 0, 0};

  for (int k = 0; k < 2; k++) {
    camera_fb_t *oldFb = esp_camera_fb_get();
    if (oldFb) {
      esp_camera_fb_return(oldFb);
      Serial.println("Discarded stale frame.");
    }
    delay(80);
  }

  //capture 3 photos
  for (int i = 0; i < NUM_PHOTOS; i++) {
    Serial.print("Capturing fresh photo ");
    Serial.println(i + 1);

    camera_fb_t *fb = esp_camera_fb_get();

    if (!fb) {
      Serial.println("Camera capture failed.");
      continue;
    }

    photoLen[i] = fb->len;

    photoData[i] = (uint8_t*)ps_malloc(photoLen[i]);
    if (!photoData[i]) {
      Serial.println("PSRAM malloc failed for photo copy. Trying normal malloc...");
      photoData[i] = (uint8_t*)malloc(photoLen[i]);
    }

    if (!photoData[i]) {
      Serial.println("Photo copy allocation failed.");
      esp_camera_fb_return(fb);
      continue;
    }

    memcpy(photoData[i], fb->buf, photoLen[i]);

    Serial.print("Stored photo ");
    Serial.print(i + 1);
    Serial.print(", size=");
    Serial.println(photoLen[i]);

    esp_camera_fb_return(fb);

    delay(333);  //3 photos in about 1 second
  }

  for (int i = 0; i < NUM_PHOTOS; i++) {
    if (!photoData[i] || photoLen[i] == 0) {
      Serial.print("Skipping photo ");
      Serial.print(i + 1);
      Serial.println(" because capture/copy failed.");
      continue;
    }

    Serial.print("Uploading stored photo ");
    Serial.println(i + 1);

    bool ok = httpPostBytes("/upload_image", "image/jpeg", photoData[i], photoLen[i]);

    if (ok) {
      Serial.println("Image upload successful.");
    } else {
      Serial.println("Image upload failed.");
    }

    free(photoData[i]);
    photoData[i] = nullptr;
  }

  busyCamera = false;
}

// =======================
// WAV header
// =======================
void writeWavHeader(uint8_t* header, uint32_t dataSize) {
  uint32_t fileSize = dataSize + 36;
  uint32_t byteRate = SAMPLE_RATE * CHANNELS * BITS_PER_SAMPLE / 8;
  uint16_t blockAlign = CHANNELS * BITS_PER_SAMPLE / 8;

  memcpy(header + 0, "RIFF", 4);

  header[4] = fileSize & 0xff;
  header[5] = (fileSize >> 8) & 0xff;
  header[6] = (fileSize >> 16) & 0xff;
  header[7] = (fileSize >> 24) & 0xff;

  memcpy(header + 8, "WAVE", 4);

  memcpy(header + 12, "fmt ", 4);
  header[16] = 16;
  header[17] = 0;
  header[18] = 0;
  header[19] = 0;

  header[20] = 1;
  header[21] = 0;

  header[22] = CHANNELS;
  header[23] = 0;

  header[24] = SAMPLE_RATE & 0xff;
  header[25] = (SAMPLE_RATE >> 8) & 0xff;
  header[26] = (SAMPLE_RATE >> 16) & 0xff;
  header[27] = (SAMPLE_RATE >> 24) & 0xff;

  header[28] = byteRate & 0xff;
  header[29] = (byteRate >> 8) & 0xff;
  header[30] = (byteRate >> 16) & 0xff;
  header[31] = (byteRate >> 24) & 0xff;

  header[32] = blockAlign & 0xff;
  header[33] = (blockAlign >> 8) & 0xff;

  header[34] = BITS_PER_SAMPLE;
  header[35] = 0;

  memcpy(header + 36, "data", 4);

  header[40] = dataSize & 0xff;
  header[41] = (dataSize >> 8) & 0xff;
  header[42] = (dataSize >> 16) & 0xff;
  header[43] = (dataSize >> 24) & 0xff;
}

// =======================
// Record and upload audio
// =======================
void recordAndUploadAudio() {
  if (busyAudio) {
    return;
  }

  busyAudio = true;

  const uint32_t numSamples = SAMPLE_RATE * RECORD_SECONDS;
  const uint32_t pcmSize = numSamples * 2;
  const uint32_t wavSize = pcmSize + 44;

  Serial.println("Audio trigger detected.");
  Serial.print("Recording ");
  Serial.print(RECORD_SECONDS);
  Serial.println(" seconds...");

  uint8_t* wavBuffer = (uint8_t*)ps_malloc(wavSize);

  if (!wavBuffer) {
    Serial.println("PSRAM allocation failed. Trying malloc...");
    wavBuffer = (uint8_t*)malloc(wavSize);
  }

  if (!wavBuffer) {
    Serial.println("Audio memory allocation failed.");
    lastAudioTriggerTime = millis();
    busyAudio = false;
    return;
  }

  writeWavHeader(wavBuffer, pcmSize);

  uint8_t* pcmPtr = wavBuffer + 44;

  for (uint32_t i = 0; i < numSamples; i++) {
    int sample = I2S.read();

    int centered = sample - 1400;
    centered = centered * 12;

    if (centered > 32767) centered = 32767;
    if (centered < -32768) centered = -32768;

    int16_t s16 = (int16_t)centered;

    pcmPtr[2 * i] = s16 & 0xff;
    pcmPtr[2 * i + 1] = (s16 >> 8) & 0xff;
  }

  Serial.println("Audio recording finished.");

  bool ok = httpPostBytes("/upload_audio", "audio/wav", wavBuffer, wavSize);

  if (ok) {
    Serial.println("Audio upload successful.");
  } else {
    Serial.println("Audio upload failed.");
  }

  free(wavBuffer);

  lastAudioTriggerTime = millis();
  busyAudio = false;
}

// =======================
// Check microphone trigger
// =======================
void checkMicTrigger() {
  if (busyAudio || busyCamera) {
    return;
  }

  bool cooldownOver = millis() - lastAudioTriggerTime > AUDIO_COOLDOWN_MS;

  if (!cooldownOver) {
    return;
  }

  const int windowSize = 200;
  long loudnessSum = 0;
  int maxRaw = 0;

  for (int i = 0; i < windowSize; i++) {
    int sample = I2S.read();

    if (sample > maxRaw) {
      maxRaw = sample;
    }

    loudnessSum += abs(sample - 1400);
  }

  int avgLoudness = loudnessSum / windowSize;

  static unsigned long lastPrint = 0;

  if (millis() - lastPrint > 1000) {
    Serial.print("mic maxRaw=");
    Serial.print(maxRaw);
    Serial.print(" avgLoudness=");
    Serial.println(avgLoudness);
    lastPrint = millis();
  }

  bool rawTriggered = maxRaw > RAW_TRIGGER_THRESHOLD;
  bool loudnessTriggered = avgLoudness > LOUDNESS_TRIGGER_THRESHOLD;

  if (rawTriggered || loudnessTriggered) {
    recordAndUploadAudio();
  }
}

// =======================
// BLE callbacks
// =======================
class ServerCallback : public BLEServerCallbacks {
  void onConnect(BLEServer *server) override {
    Serial.println("BLE client connected.");
  }

  void onDisconnect(BLEServer *server) override {
    Serial.println("BLE client disconnected. Restarting advertising...");
    delay(500);
    BLEDevice::startAdvertising();
  }
};

class TriggerCallback : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *characteristic) override {
    String value = characteristic->getValue();

    if (value.length() > 0) {
      Serial.print("Received BLE message: ");
      Serial.println(value);

      if (value == "GRAB") {
        grabRequested = true;
      }
    }
  }
};

// =======================
// Setup
// =======================
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("Starting Sentinel ESP32-S3 Sense node...");

  if (psramFound()) {
    Serial.println("PSRAM found.");
  } else {
    Serial.println("PSRAM NOT found. Enable Tools -> PSRAM -> OPI PSRAM.");
  }

  connectWiFi();

  if (!initCamera()) {
    Serial.println("Camera failed. Stop.");
    while (1) {
      delay(1000);
    }
  }

  I2S.setPinsPdmRx(MIC_CLK_PIN, MIC_DATA_PIN);

  if (!I2S.begin(I2S_MODE_PDM_RX,
                 SAMPLE_RATE,
                 I2S_DATA_BIT_WIDTH_16BIT,
                 I2S_SLOT_MODE_MONO)) {
    Serial.println("Failed to initialize I2S microphone!");
    while (1) {
      delay(1000);
    }
  }

  Serial.println("Microphone initialized.");

  BLEDevice::init("Sentinel_ESP32");

  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(new ServerCallback());

  BLEService *service = server->createService(SERVICE_UUID);

  BLECharacteristic *triggerCharacteristic = service->createCharacteristic(
    CHARACTERISTIC_UUID,
    BLECharacteristic::PROPERTY_WRITE
  );

  triggerCharacteristic->setCallbacks(new TriggerCallback());

  service->start();

  advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(SERVICE_UUID);
  advertising->setScanResponse(true);
  advertising->setMinPreferred(0x06);
  advertising->setMaxPreferred(0x12);

  BLEDevice::startAdvertising();

  Serial.println("ESP32-S3 ready.");
  Serial.println("Waiting for BLE GRAB and microphone trigger...");
}

// =======================
// Loop
// =======================
void loop() {
  if (grabRequested) {
    grabRequested = false;
    captureThreePhotos();
  }

  checkMicTrigger();

  delay(20);
}
