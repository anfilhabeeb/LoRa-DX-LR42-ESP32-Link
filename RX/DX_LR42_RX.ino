#include <Arduino.h>

// DX-LR42 receiver for ESP32 DevKit V1.
// GPIO17 (TX2) -> radio RXD; GPIO16 (RX2) <- radio TXD; GND -> GND.
// Configure this to match the UART baud stored inside the radio.
static const int RADIO_RX_PIN = 16;
static const int RADIO_TX_PIN = 17;
static const uint32_t RADIO_BAUD = 9600;

HardwareSerial Radio(2);
String inputLine;
uint32_t lastSequence = 0;
bool haveSequence = false;

void processLine(String line) {
  line.trim();
  if (!line.length()) return;

  Serial.print("[RX] Received: ");
  Serial.println(line);

  if (!line.startsWith("DATA,")) {
    Serial.println("[RX] Ignored: unknown packet format");
    return;
  }

  int firstComma = line.indexOf(',');
  int secondComma = line.indexOf(',', firstComma + 1);
  if (firstComma < 0 || secondComma < 0) {
    Serial.println("[RX] Ignored: malformed DATA packet");
    return;
  }

  uint32_t seq = (uint32_t)line.substring(firstComma + 1, secondComma).toInt();
  String message = line.substring(secondComma + 1);

  if (!haveSequence || seq != lastSequence) {
    Serial.printf("[RX] New message, sequence %lu: %s\n",
                  (unsigned long)seq, message.c_str());
    lastSequence = seq;
    haveSequence = true;
  } else {
    Serial.printf("[RX] Duplicate sequence %lu\n", (unsigned long)seq);
  }

  // ACK duplicates too, in case the previous ACK was lost.
  String ack = "ACK," + String(seq);
  Radio.println(ack);
  Serial.print("[RX] Sent: ");
  Serial.println(ack);
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Radio.begin(RADIO_BAUD, SERIAL_8N1, RADIO_RX_PIN, RADIO_TX_PIN);
  Serial.println("\nDX-LR42 ESP32 RECEIVER");
  Serial.printf("Radio UART baud: %lu\n", (unsigned long)RADIO_BAUD);
  Serial.println("Receiver ready. Waiting for radio data...");
}

void loop() {
  while (Radio.available()) {
    char c = (char)Radio.read();
    if (c == '\n') {
      processLine(inputLine);
      inputLine = "";
    } else if (c != '\r') {
      if (inputLine.length() < 180) inputLine += c;
      else {
        inputLine = "";
        Serial.println("[RX] Warning: input line exceeded buffer limit");
      }
    }
  }
}
