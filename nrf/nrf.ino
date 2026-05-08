#include <Wire.h>
#include <math.h>
#include <ArduinoBLE.h>

// =======================
// BLE settings
// =======================
const char* targetName = "Sentinel_ESP32";
const char* characteristicUuid = "abcd1234-5678-1234-5678-abcdef123456";

// =======================
// MPU6050 settings
// =======================
#define MPU6050_ADDR 0x68

#define PWR_MGMT_1     0x6B
#define ACCEL_CONFIG   0x1C
#define ACCEL_XOUT_H   0x3B

// =======================
// FSR settings
// =======================
#define FSR_PIN A0

// Adjust these after testing
const int PRESSURE_THRESHOLD = 800;
const float MOVEMENT_THRESHOLD_G = 0.30;

// Prevent spamming GRAB
const unsigned long GRAB_COOLDOWN_MS = 3000;
unsigned long lastGrabTime = 0;

// =======================
// FSR average
// =======================
int readFSRAverage() {
  long sum = 0;
  const int N = 20;

  for (int i = 0; i < N; i++) {
    sum += analogRead(FSR_PIN);
    delay(1);
  }

  return sum / N;
}

// =======================
// MPU6050 helpers
// =======================
void writeMPU6050(uint8_t reg, uint8_t data) {
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(reg);
  Wire.write(data);
  Wire.endTransmission();
}

bool readMPU6050Bytes(uint8_t startReg, uint8_t count, uint8_t *buffer) {
  Wire.beginTransmission(MPU6050_ADDR);
  Wire.write(startReg);

  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  uint8_t received = Wire.requestFrom(MPU6050_ADDR, count);

  if (received != count) {
    return false;
  }

  for (uint8_t i = 0; i < count; i++) {
    buffer[i] = Wire.read();
  }

  return true;
}

int16_t combineBytes(uint8_t highByte, uint8_t lowByte) {
  return (int16_t)((highByte << 8) | lowByte);
}

bool readAcceleration(float &ax, float &ay, float &az) {
  uint8_t data[6];

  if (!readMPU6050Bytes(ACCEL_XOUT_H, 6, data)) {
    return false;
  }

  int16_t rawAx = combineBytes(data[0], data[1]);
  int16_t rawAy = combineBytes(data[2], data[3]);
  int16_t rawAz = combineBytes(data[4], data[5]);

  //accelerometer range = ±2g sensitivity = 16384 LSB/g
  ax = rawAx / 16384.0;
  ay = rawAy / 16384.0;
  az = rawAz / 16384.0;

  return true;
}

void setupMPU6050() {
  // Wake up MPU6050
  writeMPU6050(PWR_MGMT_1, 0x00);
  delay(100);

  // Set accelerometer range to ±2g
  writeMPU6050(ACCEL_CONFIG, 0x00);
  delay(50);
}

// =======================
// Cleaner BLE debug connection helper
// =======================
BLEDevice connectToESP32() {
  Serial.println("Scanning for ESP32-S3...");
  BLE.scan();

  unsigned long lastStatusPrint = 0;
  int seenCount = 0;

  while (true) {
    BLEDevice peripheral = BLE.available();

    if (peripheral) {
      seenCount++;

      String name = peripheral.localName();
      String address = peripheral.address();

      bool hasName = name.length() > 0;
      bool nameMatches = (name == targetName);

      if (hasName) {
        Serial.print("Found BLE device: ");
        Serial.print("name=");
        Serial.print(name);
        Serial.print(" address=");
        Serial.println(address);
      }

      if (nameMatches) {
        BLE.stopScan();

        Serial.println("Matched Sentinel_ESP32. Connecting...");

        if (!peripheral.connect()) {
          Serial.println("Connection failed. Restarting scan...");
          delay(1000);
          BLE.scan();
          continue;
        }

        Serial.println("Connected to ESP32-S3. Discovering attributes...");

        if (!peripheral.discoverAttributes()) {
          Serial.println("Attribute discovery failed. Disconnecting...");
          peripheral.disconnect();
          delay(1000);
          BLE.scan();
          continue;
        }

        BLECharacteristic triggerChar = peripheral.characteristic(characteristicUuid);

        if (!triggerChar) {
          Serial.println("Trigger characteristic not found. Disconnecting...");
          peripheral.disconnect();
          delay(1000);
          BLE.scan();
          continue;
        }

        if (!triggerChar.canWrite()) {
          Serial.println("Trigger characteristic found, but not writable. Disconnecting...");
          peripheral.disconnect();
          delay(1000);
          BLE.scan();
          continue;
        }

        Serial.println("BLE link ready.");
        return peripheral;
      }
    }

    if (millis() - lastStatusPrint > 3000) {
      Serial.print("Still scanning... devices seen=");
      Serial.println(seenCount);
      lastStatusPrint = millis();
    }

    delay(50);
  }
}

// =======================
// Setup
// =======================
void setup() {
  Serial.begin(115200);
  while (!Serial);

  analogReadResolution(12);

  Wire.begin();
  setupMPU6050();

  if (!BLE.begin()) {
    Serial.println("Failed to start BLE.");
    while (1) {
      delay(1000);
    }
  }

  Serial.println("nRF52840 FSR + MPU6050 + BLE sender started.");
}

// =======================
// Main loop
// =======================
void loop() {
  BLEDevice esp32 = connectToESP32();

  BLECharacteristic triggerChar = esp32.characteristic(characteristicUuid);

  if (!triggerChar || !triggerChar.canWrite()) {
    Serial.println("BLE trigger characteristic not found/writable.");
    esp32.disconnect();
    delay(1000);
    return;
  }

  Serial.println("Entering sensor monitor loop.");

  while (esp32.connected()) {
    int pressure = readFSRAverage();

    float ax, ay, az;

    if (!readAcceleration(ax, ay, az)) {
      Serial.println("MPU6050_READ_FAILED");
      delay(200);
      continue;
    }

    float accelMag = sqrt(ax * ax + ay * ay + az * az);
    float movement = fabs(accelMag - 1.0);

    bool pressureDetected = pressure > PRESSURE_THRESHOLD;
    bool movementDetected = movement > MOVEMENT_THRESHOLD_G;
    bool cooldownOver = millis() - lastGrabTime > GRAB_COOLDOWN_MS;

    Serial.print("pressure=");
    Serial.print(pressure);

    Serial.print(" ax=");
    Serial.print(ax, 2);

    Serial.print(" ay=");
    Serial.print(ay, 2);

    Serial.print(" az=");
    Serial.print(az, 2);

    Serial.print(" movement=");
    Serial.print(movement, 2);

    if (pressureDetected && movementDetected && cooldownOver) {
      Serial.print(" GRAB");

      bool ok = triggerChar.writeValue("GRAB");

      if (ok) {
        Serial.print(" SENT");
      } else {
        Serial.print(" SEND_FAILED");
      }

      lastGrabTime = millis();
    }

    Serial.println();

    delay(100);
  }

  Serial.println("ESP32 disconnected. Reconnecting...");
  delay(1000);
}