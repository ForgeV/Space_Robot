import ubluetooth
import uasyncio as asyncio
from machine import Pin, PWM, UART, SPI
import neopixel


try:
    from mfrc522 import MFRC522
except ImportError:
    MFRC522 = None
    print("mfrc522 not found")


led = Pin(2, Pin.OUT)
led.value(0)

# моторы (ENA, IN1, IN2 / ENB, IN3, IN4)
ena = PWM(Pin(25), freq=1000, duty=0)
in1, in2 = Pin(26, Pin.OUT), Pin(27, Pin.OUT)
enb = PWM(Pin(22), freq=1000, duty=0)
in3, in4 = Pin(32, Pin.OUT), Pin(33, Pin.OUT)

# сервоприводы
srv1 = PWM(Pin(13), freq=50, duty=76)
srv2 = PWM(Pin(14), freq=50, duty=76)

# сканер
qr = UART(2, baudrate=9600, tx=17, rx=16)

# светодиодное кольцо  настроить NUM_LEDS
NUM_LEDS = ####
np = neopixel.NeoPixel(Pin(15), NUM_LEDS)
np.fill((0, 0, 0))
np.write()

# RFID
spi = SPI(2, baudrate=2500000, polarity=0, phase=0, sck=Pin(18), mosi=Pin(23), miso=Pin(19))
rfid = MFRC522(spi, 5, 4) if MFRC522 else None


def drive(l_speed, r_speed):
    # управление левым мотором
    in1.value(1) if l_speed > 0 else in1.value(0)
    in2.value(1) if l_speed < 0 else in2.value(0)
    ena.duty(abs(l_speed))
    
    # управление правым мотором
    in3.value(1) if r_speed > 0 else in3.value(0)
    in4.value(1) if r_speed < 0 else in4.value(0)
    enb.duty(abs(r_speed))

class BLEUART:
    def __init__(self, name="Space_Pirates"):
        self.b = ubluetooth.BLE()
        self.b.active(True)
        self.b.irq(self.cb)
        ((self.tx, self.rx),) = self.b.gatts_register_services((
            (ubluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E"), 
            ((ubluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E"), 16), 
             (ubluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E"), 8))),
        ))
        self.adv = b'\x02\x01\x06' + bytes([len(name) + 1, 9]) + name.encode()
        self.b.gap_advertise(100, self.adv)
        self.s1_pos = 76
        self.s2_pos = 76

    def cb(self, ev, d):
        if ev == 1: 
            self.b.gap_advertise(0)
            led.value(1)
            print("Connected")
        elif ev == 2: 
            self.b.gap_advertise(100, self.adv)
            led.value(0)
            drive(0, 0)
            print("Disconnected")
        elif ev == 3:
            buf = self.b.gatts_read(self.rx)
            if len(buf) >= 8 and buf[0] == 255:
                b1, b2 = buf[5], buf[6]
                
                # движение (крестовина)
                if b1 & 1: drive(1023, 1023)
                elif b1 & 2: drive(-1023, -1023)
                elif b1 & 4: drive(-1023, 1023)
                elif b1 & 8: drive(1023, -1023)
                elif b1 == 0 and b2 == 0: drive(0, 0)
                
                # серво 1 (треугольник/крестик)
                if b2 & 1: 
                    self.s1_pos = min(127, self.s1_pos + 2)
                    srv1.duty(self.s1_pos)
                elif b2 & 4: 
                    self.s1_pos = max(25, self.s1_pos - 2)
                    srv1.duty(self.s1_pos)
                    
                # серво 2 (круг/квадрат)
                if b2 & 2: 
                    self.s2_pos = min(127, self.s2_pos + 2)
                    srv2.duty(self.s2_pos)
                elif b2 & 8: 
                    self.s2_pos = max(25, self.s2_pos - 2)
                    srv2.duty(self.s2_pos)



async def qr_task():
    while True:
        if qr.any():
            res = qr.read()
            if res:
                print(f"[QR] Data: {res.decode('utf-8', 'ignore').strip()}")
        await asyncio.sleep_ms(50)

async def rfid_task():
    if not rfid: return
    while True:
        (stat, _) = rfid.request(rfid.REQIDL)
        if stat == rfid.OK:
            (stat, raw_uid) = rfid.anticoll()
            if stat == rfid.OK:
                uid = "%02x%02x%02x%02x" % (raw_uid[0], raw_uid[1], raw_uid[2], raw_uid[3])
                print(f"[RFID] Scanned UID: {uid}")
                np.fill((0, 255, 0))
                np.write()
                await asyncio.sleep(1)
                np.fill((0, 0, 0))
                np.write()
        await asyncio.sleep_ms(100)

async def main():
    BLEUART()
    asyncio.create_task(qr_task())
    asyncio.create_task(rfid_task())
    print("System is on")
    while True:
        await asyncio.sleep(1000)

try:
    asyncio.run(main())
except KeyboardInterrupt:
    drive(0, 0)
    np.fill((0, 0, 0))
    np.write()
    led.value(0)
    print("Stopping")