#include <Arduino.h>
#include <cstring>

namespace {
constexpr int kRadarRxPin = 16;  // LD2450 TX
constexpr int kRadarTxPin = 17;  // LD2450 RX
constexpr uint32_t kRadarBaud = 256000;
constexpr size_t kFrameSize = 30;
constexpr uint8_t kHeader[] = {0xAA, 0xFF, 0x03, 0x00};
constexpr uint32_t kPartialTimeoutMs = 100;
constexpr uint32_t kSilenceWarningMs = 3000;

HardwareSerial radar(2);
uint8_t frame[kFrameSize];
size_t buffered = 0;
uint32_t lastByteMs = 0;
uint32_t lastValidFrameMs = 0;
uint32_t lastWarningMs = 0;

uint16_t readLE16(const uint8_t *data) {
  return static_cast<uint16_t>(data[0]) |
         (static_cast<uint16_t>(data[1]) << 8);
}

int16_t decodeCoordinate(const uint8_t *data) {
  const uint16_t raw = readLE16(data);
  const int16_t magnitude = static_cast<int16_t>(raw & 0x7FFF);
  // LD2450 uses sign-magnitude with 1 = positive, not two's complement.
  return (raw & 0x8000) ? magnitude : -magnitude;
}

void printTargets(const uint8_t *data) {
  unsigned count = 0;
  Serial.printf("[%lu ms]", static_cast<unsigned long>(millis()));
  for (size_t slot = 0; slot < 3; ++slot) {
    const uint8_t *target = data + 4 + slot * 8;
    // An unused target has an entirely zero-filled 8-byte record.
    // Do not discard a real target just because X or speed is zero.
    bool present = false;
    for (size_t i = 0; i < 8; ++i) {
      present = present || target[i] != 0;
    }
    if (!present) {
      continue;
    }
    ++count;
    Serial.printf(" T%u: X=%d mm Y=%d mm", static_cast<unsigned>(slot + 1),
                  static_cast<int>(decodeCoordinate(target)),
                  static_cast<int>(decodeCoordinate(target + 2)));
  }
  if (count == 0) {
    Serial.print(" No targets");
  }
  Serial.println();
}

void consumeByte(uint8_t byte, uint32_t now) {
  if (buffered != 0 && now - lastByteMs >= kPartialTimeoutMs) {
    buffered = 0;
  }
  lastByteMs = now;
  frame[buffered++] = byte;
  if (buffered < kFrameSize) {
    return;
  }

  if (std::memcmp(frame, kHeader, sizeof(kHeader)) == 0 &&
      frame[28] == 0x55 && frame[29] == 0xCC) {
    lastValidFrameMs = now;
    printTargets(frame);
    buffered = 0;
  } else {
    // Slide one byte to recover from noise, truncated frames, or a bad tail.
    // Header-looking bytes inside a payload cannot prematurely restart a frame.
    std::memmove(frame, frame + 1, kFrameSize - 1);
    buffered = kFrameSize - 1;
  }
  // Tracking reports have no checksum: header, fixed length and footer are
  // the structural validation available; payload bit errors are undetectable.
}
}  // namespace

void setup() {
  Serial.begin(115200);
  radar.setRxBufferSize(1024);
  radar.begin(kRadarBaud, SERIAL_8N1, kRadarRxPin, kRadarTxPin);
  lastValidFrameMs = millis();
  lastWarningMs = lastValidFrameMs;
  Serial.println("Module 1: Patient Tracking — LD2450 UART2 256000 baud");
  Serial.println("Waiting for tracking frames (X/Y in mm)...");
}

void loop() {
  while (radar.available() > 0) {
    consumeByte(static_cast<uint8_t>(radar.read()), millis());
  }
  const uint32_t now = millis();
  if (now - lastValidFrameMs >= kSilenceWarningMs &&
      now - lastWarningMs >= kSilenceWarningMs) {
    Serial.println("WARNING: No valid radar frames for 3 seconds; check power, wiring and radar baud rate.");
    lastWarningMs = now;
  }
  delay(1);
}
