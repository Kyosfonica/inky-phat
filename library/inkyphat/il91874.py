#
# Python library to support the black/red IL91874 e-paper driver
#
import spidev
import RPi.GPIO as GPIO
import time

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

_SPI_COMMAND = GPIO.LOW
_SPI_DATA = GPIO.HIGH

_BOOSTER_SOFT_START = 0x06
_POWER_SETTING = 0x01
_POWER_OFF = 0x02
_POWER_ON = 0x04
_PANEL_SETTING = 0x00
_OSCILLATOR_CONTROL = 0x30
_TEMP_SENSOR_ENABLE = 0x41
_RESOLUTION_SETTING = 0x61
_VCOM_DC_SETTING = 0x82
_VCOM_DATA_INTERVAL_SETTING = 0x50
_DATA_START_TRANSMISSION_1 = 0x10
_DATA_START_TRANSMISSION_2 = 0x13
_DATA_STOP = 0x11
_DISPLAY_REFRESH = 0x12
_DEEP_SLEEP = 0x07

_PARTIAL_ENTER = 0x91
_PARTIAL_EXIT = 0x91
_PARTIAL_CONFIG = 0x90

WHITE = 0
BLACK = 1
RED = 2

class IL91874:

    def __init__(self, resolution=(264, 176), cs_pin=0, dc_pin=22, reset_pin=27, busy_pin=17, h_flip=False, v_flip=False):
        self.palette = (WHITE, BLACK, RED)
        self.resolution = resolution
        self.width, self.height = resolution

        self.b_buf = [0] * ((self.width * self.height) / 8)
        self.r_buf = [0] * ((self.width * self.height) / 8)

        self.buffer = [[0] * self.width] * self.height

        self.dc_pin = dc_pin
        self.reset_pin = reset_pin
        self.busy_pin = busy_pin
        self.cs_pin = cs_pin
        self.h_flip = h_flip
        self.v_flip = v_flip

        GPIO.setup(self.dc_pin, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(self.reset_pin, GPIO.OUT, initial=GPIO.HIGH)
        GPIO.setup(self.busy_pin, GPIO.IN)

        self._spi = spidev.SpiDev()
        self._spi.open(0, self.cs_pin)

        self.reset()

        self._busy_wait()    # wait for driver to be ready to talk

        self._send_command(_POWER_SETTING, [0x07, 0x00, 0x0A, 0x00])
        self._send_command(_BOOSTER_SOFT_START, [0x07, 0x07, 0x07])
        self._send_command(_POWER_ON)

        self._busy_wait()    # wait for driver to be ready to talk

        self._send_command(_PANEL_SETTING, [0b11001111])
        self._send_command(_VCOM_DATA_INTERVAL_SETTING, [0b00000111])

        self._send_command(_OSCILLATOR_CONTROL, [0x29])
        self._send_command(_RESOLUTION_SETTING, [0x68, 0x00, 0xD4])
        self._send_command(_VCOM_DC_SETTING, [0x0A])
        self._send_command(0x20, [0x06, 0x06, 0x06, 0x0A, 0x0A, 0x14, 0x06, 0x06, 0x06, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        self._send_command(0x21, [0x06, 0x46, 0x06, 0x8a, 0x4a, 0x14, 0x86, 0x06, 0x06, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        self._send_command(0x22, [0x86, 0x06, 0x06, 0x8a, 0x4a, 0x14, 0x06, 0x46, 0x06, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        self._send_command(0x23, [0x86, 0x06, 0x06, 0x8a, 0x4a, 0x14, 0x06, 0x46, 0x06, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        self._send_command(0x24, [0x86, 0x06, 0x06, 0x8a, 0x4a, 0x14, 0x06, 0x46, 0x06, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        self._send_command(0x25, [0x18, 0x18, 0x02, 0x1e, 0x1e, 0x02, 0x04, 0x28, 0x05, 0x05, 0x1e, 0x02, 0x04, 0x02, 0x01])
        self._send_command(0x26, [0x98, 0x98, 0x02, 0x5e, 0x5e, 0x02, 0x84, 0x68, 0x05, 0x45, 0x5e, 0x02, 0x44, 0x42, 0x01])
        self._send_command(0x27, [0x18, 0x18, 0x02, 0x1e, 0x1e, 0x02, 0x04, 0x28, 0x05, 0x05, 0x1e, 0x02, 0x04, 0x02, 0x01])

        self.clear_partial_mode()

    def clear_partial_mode(self):
        self.update_x1 = 0
        self.update_x2 = self.width - 1
        self.update_y1 = 0
        self.update_y2 = self.height - 1
        self._send_command(_PARTIAL_EXIT)

    def set_partial_mode(self, vr_st, vr_ed, hr_st, hr_ed):
        self.update_x1 = hr_st
        self.update_x2 = hr_ed
        self.update_y1 = vr_st
        self.update_y2 = vr_ed

        hr_st /= 8
        hr_ed /= 8

        # vr_st - vr_ed = 0 - 212 - Actually horizontal on Inky pHAT
        # hr_st - hr_ed = 0 - 12 - Actually vertical on Inky pHAT in 13 slices of 8 vertical pixels

        self._send_command(_PARTIAL_CONFIG, [
                                                     # D7   D6   D5   D4   D3   D2   D1   D0
            0b00000000 | (hr_st & 0b11111) << 3,     #    HRST[7:3]             0    0    0
            0b00000111 | (hr_ed & 0b11111) << 3,     #    HRED[7:3]             1    1    1
            0b00000000 | (vr_st & 0b100000000) >> 8, # -    -    -    -    -    -    -   VRST[8]
            0b00000000 | (vr_st & 0b11111111),       #                VRST[7:0]
            0b00000000 | (vr_ed & 0b100000000) >> 8, # -    -    -    -    -    -    -   VRED[8]
            0b00000000 | (vr_ed & 0b11111111),       #                VRED[7:0]
            0b00000001,                              # -    -    -    -    -    -    -   PT_SCAN
        ])

        self._send_command(_PARTIAL_ENTER)

        # HRST: Horizontal start channel bank: 00h to 13h (0 to 19)
        # HRED: Horizontal end channel bank: 00h to 13h (0 to 19), HRED must be greater than HRST
        # VRST: Vertical start line: 000h to 127h (0 to 295)
        # VRED: Vertical end line: 000h to 127h (0 to 295)
        # PT_SCAN: 0 = Only in partial window, 1 = inside and outside of partial window

    def set_border(self, border):
        cmd = 0b00000111

        if border in self.palette:
            c = self.palette[border]
            if c == BLACK:
                cmd |= 0b11000000
            if c == RED:
                cmd |= 0b01000000
            if c == WHITE:
                cmd |= 0b10000000

        self._send_command(_VCOM_DATA_INTERVAL_SETTING, [cmd])

    def set_palette(self, palette):
        self.palette = palette

    def update(self):
        # start black data transmission
        self._send_command(_DATA_START_TRANSMISSION_1)
        self._send_data(self.b_buf)

        # start red data transmission
        self._send_command(_DATA_START_TRANSMISSION_2)
        self._send_data(self.r_buf)

        self._send_command(_DISPLAY_REFRESH)
        self._busy_wait()

    def _update(self):
        x1, x2 = self.update_x1, self.update_x2 + 1
        y1, y2 = self.update_y1, self.update_y2 + 1
        width = x2 - x1
        height = y2 - y1

        buf_black = [0] * ((width * height) / 8)
        buf_red = [0] * ((width * height) / 8)

        print(width, height, len(buf_black), len(buf_red))
        print(len(self.buffer), len(self.buffer[0]))

        for x in range(x1, x2):
            for y in range(y1, y2):
                pixel = self.buffer[y][x]
                buf_off = ((y - y1) * (width // 8)) + ((x - x1) // 8)
                bit_off = (x - x1) % 8
                mask = 0b11111111 ^ (0b10000000 >> bit_off)

                # clear pixel in both buffers first
                buf_black[buf_off] &= mask
                buf_red[buf_off] &= mask

                if pixel == BLACK:
                    buf_black[buf_off] |= ~mask

                if pixel == RED:
                    buf_red[buf_off] |= ~mask

        # start black data transmission
        self._send_command(_DATA_START_TRANSMISSION_1)
        self._send_data(buf_black)

        # start red data transmission
        self._send_command(_DATA_START_TRANSMISSION_2)
        self._send_data(buf_red)

        self._send_command(_DISPLAY_REFRESH)
        self._busy_wait()

    def _set_pixel(self, x, y, v):
        if v in self.palette:
            self.buffer[y][x] = self.palette[v]

    def set_pixel(self, x, y, v):
        if self.v_flip:
            x = self.resolution[0] - 1 - x

        if self.h_flip:
            y = self.resolution[1] - 1 - y

        buf_off = (y * (self.resolution[0] // 8)) + (x // 8)
        bit_off = x % 8
        mask = 0b11111111 ^ (0b10000000 >> bit_off)

        # clear pixel in both buffers first
        self.b_buf[buf_off] &= mask
        self.r_buf[buf_off] &= mask

        if v in self.palette:

            if(self.palette[v] == BLACK):
                self.b_buf[buf_off] |= ~mask

            if(self.palette[v] == RED):
                self.r_buf[buf_off] |= ~mask

    def _busy_wait(self):
        """Wait for the e-paper driver to be ready to receive commands/data.
        """
        while(GPIO.input(self.busy_pin) == GPIO.LOW):
            pass

    def reset(self):
        """Send a reset signal to the e-paper driver.
        """
        GPIO.output(self.reset_pin, GPIO.LOW)
        time.sleep(0.1)
        GPIO.output(self.reset_pin, GPIO.HIGH)
        time.sleep(0.1)
        self._busy_wait()

    def _spi_write(self, dc, values):
        GPIO.output(self.dc_pin, dc)
        self._spi.xfer(values)

    def _send_command(self, command, data = []):
        #print("Command {0:02x}".format(command))
        self._spi_write(_SPI_COMMAND, [command])
        if len(data) > 0:
            self._spi_write(_SPI_DATA, data)

    def _send_data(self, data = []):
        if len(data) > 0:
            self._spi_write(_SPI_DATA, data)
