#include <Arduino.h>

// DX-LR42 transmitter for ESP32 DevKit V1.
// GPIO17 (TX2) -> radio RXD; GPIO16 (RX2) <- radio TXD; GND -> GND.
// Configure this to match the UART baud stored inside the radio.
// 9600 is used because it was the last confirmed working speed.
static const int RADIO_RX_PIN = 16;
static const int RADIO_TX_PIN = 17;
static const uint32_t RADIO_BAUD = 9600;
static const uint32_t ACK_TIMEOUT_MS = 1200;
static const uint8_t MAX_ATTEMPTS = 3;
static const uint32_t SEND_INTERVAL_MS = 3000;

HardwareSerial Radio(2);
uint32_t sequenceNumber = 1;
uint32_t lastSendMs = 0;

String readRadioLine(uint32_t timeoutMs) {
  String line;
  uint32_t started = millis();
  while (millis() - started < timeoutMs) {
    while (Radio.available()) {
      char c = (char)Radio.read();
      if (c == '\n') { line.trim(); return line; }
      if (c != '\r' && line.length() < 120) line += c;
    }
    delay(1);
  }
  line.trim();
  return line;
}

bool waitForAck(uint32_t seq) {
  uint32_t started = millis();
  const String expected = "ACK," + String(seq);
  while (millis() - started < ACK_TIMEOUT_MS) {
    String response = readRadioLine(50);
    if (!response.length()) continue;
    Serial.print("[RADIO] ");
    Serial.println(response);
    if (response == expected) return true;
  }
  return false;
}

bool sendMessage(uint32_t seq) {
  String packet = "DATA," + String(seq) + ",Hello from ESP32 TX";
  for (uint8_t attempt = 1; attempt <= MAX_ATTEMPTS; ++attempt) {
    while (Radio.available()) Radio.read();
    Serial.printf("[TX] Attempt %u -> %s\n", attempt, packet.c_str());
    Radio.println(packet);
    if (waitForAck(seq)) {
      Serial.printf("[TX] ACK received for sequence %lu\n", (unsigned long)seq);
      return true;
    }
    Serial.println("[TX] ACK timeout");
  }
  Serial.printf("[TX] FAILED: no ACK for sequence %lu\n", (unsigned long)seq);
  return false;
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Radio.begin(RADIO_BAUD, SERIAL_8N1, RADIO_RX_PIN, RADIO_TX_PIN);
  Serial.println("\nDX-LR42 ESP32 TRANSMITTER");
  Serial.printf("Radio UART baud: %lu\n", (unsigned long)RADIO_BAUD);
  Serial.println("Transmitter ready.");
}

void loop() {
  if (millis() - lastSendMs >= SEND_INTERVAL_MS) {
    lastSendMs = millis();
    sendMessage(sequenceNumber++);
  }
}
