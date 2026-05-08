# Sentinel Project Explanation

This document explains the current Sentinel project based on the code in this repository.

## Project Overview

Sentinel is a triggered object-interaction recording system. Instead of recording all the time, it waits for signs that the user is interacting with an object, then captures nearby visual and audio context.

The system has three main parts:

- `nrf/nrf.ino`: wearable nRF52840 sensor node.
- `esp32_s3/esp32_s3.ino`: ESP32-S3 Sense camera/audio node.
- `sentinel_server.py`: Raspberry Pi 5 server that receives uploaded media.

The nRF52840 detects a possible grab or object interaction. The ESP32-S3 captures photos and audio. The Raspberry Pi 5 receives and stores the uploaded files.

## How It Works

The wearable nRF52840 is the trigger device. It reads a force-sensitive resistor and an MPU6050 accelerometer. The FSR checks whether there is enough pressure, and the accelerometer checks whether the wrist is moving. When both pressure and motion pass the thresholds, the nRF decides that a grab-like event happened.

After detecting that event, the nRF sends a `GRAB` message to the ESP32-S3 over BLE. BLE is only used for this short trigger signal.

The ESP32-S3 is the capture device mounted on the collar. It advertises itself over BLE as `Sentinel_ESP32` and waits for the `GRAB` command. When it receives `GRAB`, it captures three JPEG photos with the camera. Those photos are uploaded over Wi-Fi to the Raspberry Pi 5 server.

The ESP32-S3 also monitors its microphone. This audio path is separate from the nRF trigger. If the microphone detects a loud enough sound, the ESP32-S3 records a 3 second WAV audio clip and uploads it over Wi-Fi to the Raspberry Pi 5.

The Raspberry Pi 5 runs `sentinel_server.py`. The server receives image uploads at `/upload_image` and audio uploads at `/upload_audio`. It saves images into `received_images` and audio clips into `received_audio`.

In short:

- BLE carries the `GRAB` trigger from the wearable nRF52840 to the ESP32-S3.
- Wi-Fi carries the heavier media files from the ESP32-S3 to the Raspberry Pi 5.
- The Raspberry Pi 5 stores the captured pictures object detection and audio for parsing.

## Main Hardware

### Wearable Node

The wearable node uses:

- XIAO nRF52840 or compatible ArduinoBLE board.
- One FSR pressure sensor on `A0`. (Ideally optimized to four sensors distributed around the waist)
- MPU6050 accelerometer over I2C.
- BLE connection to the ESP32-S3.

### Capture Node

The capture node uses:

- XIAO ESP32-S3 Sense.
- Onboard camera.
- PDM microphone.
- BLE for receiving `GRAB`.
- Wi-Fi for uploading media.

### Raspberry Pi 5 Server

The Raspberry Pi 5 runs a server and the higher-level recognition pipeline:

- `GET /` returns a status message.
- `POST /upload_image` saves a timestamped `.jpg` file.
- `POST /upload_audio` saves a timestamped `.wav` file.

## Raspberry Pi Recognition Pipeline

After the ESP32-S3 uploads pictures and audio to the Raspberry Pi 5, the Pi is responsible for turning those files into useful "where is my item" records.

For pictures, the system uses a YOLOv8 model fine-tuned on photos of the three target objects:

- wallet
- AirPods
- phone

When a new image is received, YOLOv8 checks whether one of these objects appears in the picture. The same image is also used to recognize the surrounding environment with a local KNN network. For example, the environment model can label where the object was seen, such as a desk, room area, or other trained location category.

The result is stored in SQLite. Each record connects an object with the environment where it was last seen. Conceptually, the database stores information like:

- object: `phone`, `airpods`, or `wallet`
- location/environment: result from the local KNN network
- timestamp: when the media was received or processed
- source image path: the saved image used for recognition

For audio, the system extracts keywords from the recorded speech or sound query. The important keywords are:

- phone
- AirPods
- wallet

When one of these keywords is detected, the Raspberry Pi looks up that object in SQLite and returns the most recent environment where the object was recorded. For example, if the audio query contains "phone", the system searches the database for the latest `phone` record and uses that to answer where the phone was last seen.

## Important Specs

### nRF Trigger Specs

The nRF sends `GRAB` only when pressure and movement are both detected.

Current values:

- FSR pressure threshold: `800`.
- Movement threshold: `0.30g`.
- Trigger cooldown: `3000 ms`.

The cooldown prevents the wearable from sending too many `GRAB` messages during one continuous interaction.

### ESP32-S3 Photo Specs

When the ESP32-S3 receives `GRAB`, it captures three photos.

Current values:

- Image format: 800*600 JPEG.
- Frame size: QVGA.
- Number of photos per trigger: `3`.
- Upload endpoint: `/upload_image`.
- Transport: Wi-Fi HTTP POST.

### ESP32-S3 Audio Specs

Audio capture is triggered by microphone loudness, not by the nRF.

Current values:

- Audio format: WAV.
- Sample rate: `16000 Hz`.
- Bit depth: `16-bit`.
- Channels: mono.
- Recording length: `3 seconds`.
- Audio cooldown: `5000 ms`.
- Upload endpoint: `/upload_audio`.
- Transport: Wi-Fi HTTP POST.

## End-To-End Flow

1. ESP32-S3 starts BLE advertising and waits for triggers.
2. Raspberry Pi 5 starts the server.
3. nRF52840 scans for and connects to ESP32-S3.
4. nRF watches pressure and motion.
5. When a grab-like event is detected,  nRF sends `GRAB` over BLE.
6. ESP32-S3 captures pictures.
7. ESP32-S3 uploads the pictures to Raspberry Pi 5 over Wi-Fi.
8. Raspberry Pi 5 runs YOLOv8 to detect wallet, AirPods, or phone in the uploaded pictures.
9. Raspberry Pi 5 uses a local KNN network to recognize the environment in the image.
10. Raspberry Pi 5 stores the object, environment, timestamp, and image path in SQLite.
11. If loud audio is detected, ESP32-S3 records a WAV clip.
12. ESP32-S3 uploads the audio clip to Raspberry Pi 5 over Wi-Fi.
13. Raspberry Pi 5 extracts keywords from the audio.
14. Raspberry Pi 5 queries SQLite and finds the latest recorded environment for that object.
