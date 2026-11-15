# DX-LR42-ESP32-Link

Point-to-point wireless communication between **two ESP32 boards** using two **DX-LR42-24T12D 2.4 GHz UART RF modules**.

The repository contains separate Arduino sketches for transmitter and receiver. The transmitter sends numbered messages and waits for an application-level acknowledgement. The receiver prints each new message and replies with an ACK.

## Recommended repository name

`DX-LR42-ESP32-Link`

## Hardware

- 2 × ESP32 DevKit V1 (or compatible ESP32 boards)
- 2 × DX-LR42-24T12D 2.4 GHz UART RF modules
- Suitable regulated power supply for each radio
- Jumper wires

The DX-PJ15-V1.1 USB-to-TTL adapter is useful for configuring/debugging a radio from a PC. It is not required in the final ESP32-to-radio wiring.

## Wiring (repeat at both nodes)

| ESP32 DevKit V1 | DX-LR42 |
|---|---|
| GPIO17 / TX2 | RXD |
| GPIO16 / RX2 | TXD |
| GND | GND |
| Suitable supply | VCC |

**Electrical notes**
- UART is crossed: ESP32 TX goes to radio RXD; ESP32 RX goes to radio TXD.
- Connect grounds together.
- The module board is marked `POWER: 3.3V–5.5V`; verify the supply requirements and current capability for your exact board.
- Use 3.3 V logic on UART signals. Do not connect ESP32 GPIOs to a 5 V UART signal.
- Do not connect M0/M1 to a voltage until you have confirmed the correct mode table and logic levels for V1.0.1.

## Radio configuration

Configure both DX-LR42 modules independently using the manufacturer's documented AT procedure, then put them into transparent data mode.

Both radios must have compatible settings:
- Same RF frequency/channel
- Same RF air data-rate level
- Compatible addressing / MAC configuration
- Compatible CRC and key/open-key settings
- Same UART baud rate, data bits, parity and stop bits

Previously reported settings for this setup:

| Parameter | Reported setting |
|---|---|
| Firmware | V1.0.1 |
| Frequency | 2424 MHz |
| RF level | 8 (reported as approximately 1 Mbps) |
| MAC | `ff,ff` |
| CRC | Enabled |
| Openkey | `0` |
| Previously confirmed UART speed | 9600 baud |

These are previously reported values, not a guarantee that every setting is correct for every firmware revision. **RF level is not UART baud rate.**

### UART baud rate

Both sketches use `9600` because that was the last UART speed reported to work reliably.

If you confirm that both radios have successfully been configured for another UART speed, change this line in **both** sketches:

```cpp
static const uint32_t RADIO_BAUD = 9600;
```

The ESP32 sketch baud must match the actual UART baud stored inside its attached DX-LR42 module. Changing the Serial Monitor baud does not change the radio's internal UART baud.

## Arduino IDE setup

1. Install Arduino IDE.
2. Install the Espressif ESP32 board package through Boards Manager.
3. Connect the transmitter ESP32 by USB.
4. Open `TX/DX_LR42_TX.ino`.
5. Select the correct ESP32 board and COM port, then upload.
6. Connect the receiver ESP32.
7. Open `RX/DX_LR42_RX.ino`.
8. Select its board and COM port, then upload.

The sketches use `HardwareSerial(2)` (UART2). The USB Serial Monitor is used for diagnostics at **115200 baud**. This is separate from the radio UART baud.

## Run the test

1. Power both ESP32/radio nodes.
2. Open the receiver Serial Monitor first, at 115200 baud.
3. Open the transmitter Serial Monitor, at 115200 baud.
4. The transmitter sends a numbered `DATA` line every three seconds.
5. The receiver prints the message and returns `ACK,<sequence>`.
6. The transmitter reports whether the ACK was received.

Example transmitter output:

```text
DX-LR42 ESP32 TRANSMITTER
Radio UART baud: 9600
[TX] Attempt 1 -> DATA,1,Hello from ESP32 TX
[RADIO] ACK,1
[TX] ACK received for sequence 1
```

Example receiver output:

```text
DX-LR42 ESP32 RECEIVER
Radio UART baud: 9600
Receiver ready. Waiting for radio data...
[RX] Received: DATA,1,Hello from ESP32 TX
[RX] New message, sequence 1: Hello from ESP32 TX
[RX] Sent: ACK,1
```

## Protocol

- Transmitter sends `DATA,<sequence>,<message>` followed by newline.
- Receiver checks the basic packet structure.
- Receiver prints a new sequence once and replies `ACK,<sequence>`.
- Receiver also ACKs duplicate sequences so a lost ACK does not cause repeated processing.
- Transmitter retries up to three times if it does not receive the matching ACK.

This is an application-level acknowledgement implemented by these sketches. It is not a claim that the DX-LR42 radio itself provides hardware-level ACK/retry.

## Troubleshooting

**No data received**
- Check radio power and common ground.
- Check crossed UART wiring (GPIO17 -> RXD; GPIO16 <- TXD).
- Confirm both radios are in transparent mode.
- Confirm matching RF frequency, RF level, addressing and other radio settings.
- Confirm radio UART speed matches `RADIO_BAUD` in both sketches.
- Ensure radio UART pins are not simultaneously connected to another active serial adapter.

**Junk characters**
- Check the UART baud configured inside the radio, not only the ESP32 sketch.
- Confirm both sides use 8-N-1.
- Verify TX/RX wiring and supply stability.
- Keep the USB Serial Monitor at 115200; this is the ESP32 debug console, not necessarily the radio UART.

**ACK timeout**
- Check whether the receiver prints the DATA packet.
- If receiver prints DATA but transmitter times out, inspect the reverse radio path and receiver TX-to-radio RXD wiring.
- Ensure bidirectional transparent communication is supported under the selected radio configuration.

## Project structure

```text
DX-LR42-ESP32-Link/
├── README.md
├── LICENSE
├── TX/
│   └── DX_LR42_TX.ino
└── RX/
    └── DX_LR42_RX.ino
```

## License

MIT License.
