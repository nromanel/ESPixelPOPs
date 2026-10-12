# ESPixel Pops

This is an attempted re-creation based on the original materials. It is not
the author's released board file.

A one-output Wi-Fi pixel controller for an ESP-01 module. The circuit is the
Ukewarrior ESPixel Pops rev D schematic of 19 July 2017. The board is 1.80 by
1.00 inch, so the 1.00 inch side slides into 1 inch schedule-40 PVC.

Every part on the board is through-hole. Open `ESPixelPOPs.kicad_pcb` in KiCad
8 and run Edit, Fill All Zones before ordering. GND is already traced on the
back; the zone is the pour.

- [ESPixel Pops project](https://zappedmyself.com/projects/espixelpops/)
- [Original ESPixel](https://github.com/madsci1016/ESPixel)

## How it matches the build guide

J1 is the 5-position 3.81 mm terminal, wire entries facing off the left edge.

| Pin | Silk | Connect |
|---|---|---|
| 1 | VCC | supply positive |
| 2 | GND | supply negative |
| 3 | GND | pixel ground |
| 4 | DATA | pixel data |
| 5 | VCC | pixel positive |

JP1 reads GND, CTS, VCC, RX, TX, DTR from left to right. For programming,
connect adapter ground to GND, adapter TXD to RX, and adapter RXD to TX. Leave
the other three pins open. VCC on this header is the pixel supply, not 3.3 V.
Power the board from J1. The adapter cannot run the ESP-01.

The ESP-01 plugs into U2 with the antenna hanging off the right edge. D1, the
1N4148, has its band toward the header. That diode is the serial level shifter,
so a 3.3 V or a 5 V adapter can program the module.

## 5 V pixels or 12 V pixels

U1 is an LD1117V33. Its metal tab is the 3.3 V output and faces the terminal.
Do not let the tab touch the terminal screws.

| Pixels | IC1 | Silk jumper |
|---|---|---|
| 5 V | leave it empty | solder a wire between pads 1 and 3 |
| 12 V | fit the 78L05, flat side toward R1 and R2 | no jumper |

Pad 1 is the square pad. On a 12 V build the 78L05 only feeds the pixel-data
pullup. The pixels themselves still get the full 12 V from J1 pin 5. A board
built one way does not drive the other kind of pixel.

Q1 is the 2N7000 data buffer. The flat faces the terminal. The top pad is the
source, the bottom pad is the drain, and the middle pin is the gate. GPIO2
drives the pixels. Hold S1 while powering the board to enter the serial bootloader.

## Firmware

ESPixelStick 3.2 is the last release that fits an ESP-01. Pixel output is
GPIO2. Later ESPixelStick releases need a module with 4 MB of flash.
