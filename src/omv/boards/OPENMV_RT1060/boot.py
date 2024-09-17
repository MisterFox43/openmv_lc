#https://github.com/sparkfun/Qwiic_LED_Stick_Py/blob/main/qwiic_led_stick.py

import time
import machine
from machine import UART, SoftI2C, Pin

# I2C-Adresse des SparkFun Qwiic LED Stick
LED_STICK_ADDRESS = 0x23  # Standardadresse des LED Sticks

COMMAND_CHANGE_ADDRESS = 0xC7
COMMAND_CHANGE_LED_LENGTH = 0x70
COMMAND_WRITE_SINGLE_LED_COLOR = 0x71
COMMAND_WRITE_ALL_LED_COLOR = 0x72
COMMAND_WRITE_RED_ARRAY = 0x73
COMMAND_WRITE_GREEN_ARRAY = 0x74
COMMAND_WRITE_BLUE_ARRAY = 0x75
COMMAND_WRITE_SINGLE_LED_BRIGHTNESS = 0x76
COMMAND_WRITE_ALL_LED_BRIGHTNESS = 0x77
COMMAND_WRITE_ALL_LED_OFF = 0x78

lednum=10

# Initialisiere I2C auf der OpenMV-Kamera (SCL=Pin B6, SDA=Pin B7)
#i2c = machine.I2C(1, freq=400000)


i2c  = SoftI2C(scl=Pin('P0'), sda=Pin('P1'), freq=100000)
print("I2C Devices:",i2c.scan())

def set_led_color(led_index, red, green, blue):
    #Setzt die Farbe einer einzelnen LED.

    i2c.writeto(LED_STICK_ADDRESS,
                bytearray([COMMAND_WRITE_SINGLE_LED_COLOR])
                +led_index.to_bytes(1, 'big')
                +red.to_bytes(1, 'big')
                +green.to_bytes(1, 'big')
                +blue.to_bytes(1, 'big'))

def set_all_ledcolor(red, green, blue):
    #Setzt die Farbe einer einzelnen LED.

    i2c.writeto(LED_STICK_ADDRESS,
                bytearray([COMMAND_WRITE_ALL_LED_COLOR])
                +red.to_bytes(1, 'big')
                +green.to_bytes(1, 'big')
                +blue.to_bytes(1, 'big'))

def clear_leds():
    #Setzt alle LEDs zurück (aus).

    i2c.writeto(LED_STICK_ADDRESS, bytearray([0x78]))

def fade():
    for i in range(lednum):
        set_led_color(i,0,0,i*10+10)
        set_led_color(i-1,0,0,0)
        print(i,lednum)
        if i==lednum-1:
            for n in range(lednum):
                set_led_color(lednum-n,0,n*10,i*10)
                set_led_color(lednum-n+1,0,0,0)
                print(n)
                time.sleep(0.1)

        time.sleep(0.1)


while True:

    # to the IDE. The FPS should increase once disconnected.

    #clear_leds()
    """
    for i in range(lednum):
        set_led_color(i,2,2,2)
        time.sleep(0.005)
    """

    time.sleep(1)
    set_all_ledcolor(6,6,6)
    time.sleep(1)
    set_led_color(5,100,6,6)



