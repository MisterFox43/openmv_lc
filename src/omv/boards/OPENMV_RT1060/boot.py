#Copyright 2024, Maximilian Haidn, All rights reserved.

import sensor
import ustruct
import time
import machine
import image
from machine import UART, SoftI2C, Pin
from image import SEARCH_EX

version_text="OPENMV_MX_Machinevision_Recom_v1.0 \r\n"


i=0
usb_ena=False
if usb_ena:
    usb = USB_VCP()
else:
    usb = UART(1 , 115200 , timeout_char=50)

FCT="Null"
CMD="Null"
VALUE="Null"
recd_str="None"

#i2c = machine.I2C(1, freq=400000)
i2c  = SoftI2C(scl=Pin('P0'), sda=Pin('P1'), freq=100000)
#i2cs  = SoftI2C(scl=Pin('P1'), sda=Pin('P0'), freq=100000)
print("I2C Devices:",i2c.scan())

EXPOSURE_MICROSECONDS = 20000 #4000
TRACKING_RESOLUTION = sensor.QQVGA
sensor.reset()
sensor.set_pixformat(sensor.RGB565)
sensor.set_framesize(sensor.VGA)
sensor.skip_frames(time=1000)
sensor.set_auto_exposure(False, exposure_us=EXPOSURE_MICROSECONDS)
sensor.set_auto_gain(False, gain_db=20)
sensor.set_auto_whitebal(False)
clock = time.clock()

template24 = image.Image("/template24V.pgm")
template48 = image.Image("/template48V.pgm")
templatefid = image.Image("/templatefid.pgm")

thresholds = [
(25, 100, -128, -26, -128, 127),
]


thresholds_dip = [
(33, 62, 127, -128, -128, 127),
]

#QQVGA
led_roi=[(61,20,11,34),
     (91,28,13,12),
     (104,28,13,12),
     (117,28,13,12),
     (130,28,13,12)]
#VGA
dip_roi=[(279,334,20,30),
    (305,334,20,30)]
dip_roi_sanity=[(0,0,0,0),
                (0,0,0,0)]
for n, roi in enumerate (dip_roi):
   dip_roi_sanity[n]=tuple(map(lambda i, j: i + j, roi, (0,-38,0,0)))
print(dip_roi_sanity)

#VGA
template_roi=(435,0,70,50)
positionmatch_roi=(351,239,221,165)
locked_template_pos=(0,0,0,0)
offset_roi=(0,0,0,0)
offset_new=(0,0,0,0)
Led=[0,0,0,0,0]
Dip=[0,0,0,0,0]
Dip_s=[0,0,0,0,0]

#APA102C
led_array_set=(0,0,0,0)
w = 500
h = 400
x=-300
y=-100

def positionmatch():
    sensorpixformat=sensor.get_pixformat()
    sensorframesize=sensor.get_framesize()
    sensor.set_framesize(sensor.VGA)
    sensor.set_pixformat(sensor.GRAYSCALE)
    sensor.set_auto_exposure(False, exposure_us=10000)
    sensor.set_auto_gain(False, gain_db=20)
    set_all_ledcolor(100, 100, 100)
    time.sleep_ms(200)
    img = sensor.snapshot()
    time.sleep_ms(50)
    img.draw_rectangle(positionmatch_roi)
    r = img.find_template(
        templatefid, 0.70, step=4, search=SEARCH_EX, roi=positionmatch_roi)
    if r:
        img.draw_rectangle(r)
        sensor.set_pixformat(sensorpixformat)
        sensor.set_framesize(sensorframesize)
        print("Position Found")
        return(r)

    img = sensor.snapshot()
    i2c.writeto(0x23, bytearray([0x78]))
    time.sleep(0.1)
    sensor.set_pixformat(sensorpixformat)
    sensor.set_framesize(sensorframesize)
    return("None")


def templatematch():
    sensorpixformat=sensor.get_pixformat()
    sensorframesize=sensor.get_framesize()
    sensor.set_framesize(sensor.VGA)
    sensor.set_pixformat(sensor.GRAYSCALE)
    sensor.set_auto_exposure(False, exposure_us=10000)
    sensor.set_auto_gain(False, gain_db=20)
    set_all_ledcolor(100, 100, 100)
    time.sleep_ms(200)
    img = sensor.snapshot()
    time.sleep_ms(50)
    img.draw_rectangle(template_roi)
    r = img.find_template(
        template24, 0.70, step=4, search=SEARCH_EX, roi=template_roi)
    if r:
        img.draw_rectangle(r)
        sensor.set_pixformat(sensorpixformat)
        sensor.set_framesize(sensorframesize)

        return("24V")

    r = img.find_template(
        template48, 0.70, step=4, search=SEARCH_EX, roi=template_roi)
    if r:
        img.draw_rectangle(r)
        img.draw_string(r[0],r[1],"48",color=(255, 255, 255),scale=2,)
        sensor.set_pixformat(sensorpixformat)
        sensor.set_framesize(sensorframesize)
        return("48V")
    img = sensor.snapshot()
    i2c.writeto(0x23, bytearray([0x78]))
    time.sleep(0.1)
    sensor.set_pixformat(sensorpixformat)
    sensor.set_framesize(sensorframesize)
    return("None")


def dip_detect():
    sensorpixformat=sensor.get_pixformat()
    sensorframesize=sensor.get_framesize()
    sensor.set_framesize(sensor.VGA)
    sensor.set_pixformat(sensor.RGB565)
    sensor.set_auto_exposure(False, exposure_us=6000)
    sensor.set_auto_gain(False, gain_db=20)
    set_all_ledcolor(100, 100, 100)
    time.sleep_ms(200)
    img = sensor.snapshot()
    time.sleep_ms(30)
    for n, area in enumerate(dip_roi_sanity):
        Dip_s[n]=0
        for blob in img.find_blobs(
            thresholds_dip,roi=tuple(map(lambda i, j: i + j, area, offset_roi)), pixels_threshold=50, area_threshold=110, merge=True
        ):
            if blob.code() == 1:
                if blob.elongation() > 0.5:
                    img.draw_edges(blob.min_corners(), color=(255, 0, 0))
                    img.draw_line(blob.major_axis_line(), color=(0, 255, 0))
                    img.draw_line(blob.minor_axis_line(), color=(0, 0, 255))
                img.draw_rectangle(blob.rect())
                img.draw_cross(blob.cx(), blob.cy())
                Dip_s[n]=1
                #print(n,Dip_s[n])

    for n, area in enumerate(dip_roi_sanity):
        if Dip_s[n] == 1:
            img.draw_rectangle(tuple(map(lambda i, j: i + j, area, offset_roi)), color=(255,0,0))

        else:
            img.draw_rectangle(tuple(map(lambda i, j: i + j, area, offset_roi)))

    for n, area in enumerate(dip_roi):
        Dip[n]=0
        for blob in img.find_blobs(
            thresholds_dip,roi=tuple(map(lambda i, j: i + j, area, offset_roi)), pixels_threshold=39, area_threshold=20, merge=True
        ):
            if blob.code() == 1:
                if blob.elongation() > 0.5:
                    img.draw_edges(blob.min_corners(), color=(255, 0, 0))
                    img.draw_line(blob.major_axis_line(), color=(0, 255, 0))
                    img.draw_line(blob.minor_axis_line(), color=(0, 0, 255))
                img.draw_rectangle(blob.rect())
                img.draw_cross(blob.cx(), blob.cy())
                if Dip_s[n] == 0:
                    Dip[n]=1
                else:
                    Dip[n]=2
        for n, area in enumerate(dip_roi):
            if Dip[n] == 1:
                img.draw_rectangle(tuple(map(lambda i, j: i + j, area, offset_roi)), color=(255,0,0))

            else:
                if Dip_s[n] == 0:
                    Dip[n]=2
                img.draw_rectangle(tuple(map(lambda i, j: i + j, area, offset_roi)))
    img = sensor.snapshot()
    i2c.writeto(0x23, bytearray([0x78]))
    time.sleep(0.1)
    sensor.set_pixformat(sensorpixformat)
    sensor.set_framesize(sensorframesize)
    sensor.set_auto_exposure(False, exposure_us=EXPOSURE_MICROSECONDS)
    return(Dip)


def led_detect():
    sensorpixformat=sensor.get_pixformat()
    sensorframesize=sensor.get_framesize()
    EXPOSURE_MICROSECONDS = 4000 #4000
    TRACKING_RESOLUTION = sensor.QQVGA
    sensor.set_pixformat(sensor.RGB565)
    sensor.set_framesize(sensor.QQVGA)
    sensor.set_auto_exposure(False, exposure_us=EXPOSURE_MICROSECONDS)
    sensor.set_auto_gain(False, gain_db=20)
    time.sleep_ms(250)
    Ticker=0
    TickerDif=0
    LedTick=0
    LedTickDif=0
    LedON=0
    LedOFF=0
    img = sensor.snapshot()
    for n, area in enumerate(led_roi):
        Led[n]=0
        for blob in img.find_blobs(
            thresholds,roi=area, pixels_threshold=20, area_threshold=20, merge=True
        ):
            if blob.code() == 1:
                if blob.elongation() > 0.5:
                    img.draw_edges(blob.min_corners(), color=(255, 0, 0))
                    img.draw_line(blob.major_axis_line(), color=(0, 255, 0))
                    img.draw_line(blob.minor_axis_line(), color=(0, 0, 255))
                img.draw_rectangle(blob.rect())
                img.draw_cross(blob.cx(), blob.cy())
                Led[n]=1
        if Led[1]==1:
            if LedTick >0:
                LedTickDif=time.ticks_ms()-LedTick
            LedTick=time.ticks_ms()
            LedON=LedON+LedTickDif
        else:
            if LedTick>0:
               LedTickDif=time.ticks_ms()-LedTick
               LedON=LedON-LedTickDif
            LedTick=0
            LedON=0
    for n, area in enumerate(led_roi):
        if Led[n] == 1:
            img.draw_rectangle(area, color=(255,0,0))
        else:
            img.draw_rectangle(area)
        n=n+1
    TickerDif=time.ticks_ms()-Ticker
    Ticker=time.ticks_ms()
    sensor.set_pixformat(sensorpixformat)
    sensor.set_framesize(sensorframesize)
    sensor.set_auto_exposure(False, exposure_us=EXPOSURE_MICROSECONDS)
    return(Led)


def set_led_color(led_index, red, green, blue):
    i2c.writeto(0x23,
                bytearray([0x71])
                +led_index.to_bytes(1, 'big')
                +red.to_bytes(1, 'big')
                +green.to_bytes(1, 'big')
                +blue.to_bytes(1, 'big'))


def set_all_ledcolor(red, green, blue):
    i2c.writeto(0x23,
                bytearray([0x72])
                +red.to_bytes(1, 'big')
                +green.to_bytes(1, 'big')
                +blue.to_bytes(1, 'big'))


time.sleep(0.2)
locked_template_pos=positionmatch()
print(locked_template_pos)
offset_new = list(offset_new)
offset_new[0]=locked_template_pos[0]-410 #X-Offset
offset_new[1]=locked_template_pos[1]-297 #Y-Offset
offset_roi = tuple(offset_new)
print(offset_roi)


while True:
    clock.tick()
    img = sensor.snapshot()
    if usb.any():
        try:
            recd_data=usb.read()
            recd_data=str(recd_data)
            recd_data=recd_data.strip("b'")
            recd_data=recd_data[:-4]
            print(recd_data)
            scpi_chain = recd_data.split(':')
            for idsc, sc in enumerate(scpi_chain):
                if idsc==0:
                    FCT=sc
                if idsc==1:
                    CMD=sc
                if idsc==2:
                    VALUE=sc
            if FCT == '*IDN?':
                usb.write(version_text)
                print("idn sent")
                time.sleep_ms(100)
            elif FCT == "MEAS":
                if CMD == "POS":
                    usb.write("69")
            elif FCT == "GET":
                if CMD:
                    if CMD == "PIC":
                        img = img.compress(quality=100)
                        usb.write(ustruct.pack("<L", img.size()))
                        usb.write(img)
                    if CMD == "LEDS?":
                        Led=led_detect()
                        for ld in Led:
                            usb.write(str(ld))
                        usb.write("\r\n")
                    if CMD == "MODEL?":
                        usb.write(templatematch())
                        usb.write("\r\n")
                    if CMD == "DIP?":
                        Dip=dip_detect()
                        for dp in Dip:
                            usb.write(str(dp))
                        usb.write("\r\n")
                    if CMD == "DIP_ROI?":
                        usb.write(dip_roi)
                        usb.write("\r\n")
                    if CMD == "LED_ROI?":
                        usb.write(led_roi)
                        usb.write("\r\n")
                    if CMD == "MODEL_ROI?":
                        usb.write(model_roi)
                        usb.write("\r\n")
                    if CMD == "OFFSET_ROI?":
                        usb.write(offset_roi)
                        usb.write("\r\n")
                    if CMD == "INFO?":
                        usb.write("Commands: GET: PIC, DIP_ROI?,MODEL?,LED_ROI?,MODEL_ROI?,OFFSET_ROI?,INFO?  \r\n")
                        usb.write("SET: LED_SET:(n,r,g,b), DIP_ROI:(x,y,w,h),LED_ROI:(x,y,w,h),MODEL_ROI:(x,y,w,h),OFFSET_ROI::(x,y,w,h)\r\n")
                        usb.write("\r\n")


            elif FCT == "SET":
                if CMD:
                    if CMD == "LED_SET":
                        VALUE=VALUE.strip()
                        led_array_set=VALUE
                        print(VALUE)
                        set_led_color(led_array_set[0],led_array_set[1],led_array_set[2],led_array_set[3])
                    if CMD == "LED_CLEAR":
                        set_all_ledcolor(0, 0, 0)
                    if CMD == "DIP_ROI":
                        VALUE=VALUE.strip()
                        print(VALUE)
                        dip_roi=VALUE
                        print(dip_roi)
                    if CMD == "LED_ROI":
                        VALUE=VALUE.strip()
                        print(VALUE)
                        led_roi=VALUE
                        print(dip_roi)
                    if CMD == "MODEL_ROI":
                        VALUE=VALUE.strip()
                        print(VALUE)
                        template_roi=VALUE
                        print(dip_roi)
                    if CMD == "OFFSET_ROI":
                        VALUE=VALUE.strip()
                        print(VALUE)
                        offset_roi=VALUE
                        print(offset_roi)

            for sc in scpi_chain:
                del sc
            FCT="Null"
            CMD="Null"
            VALUE="Null"
        except (TypeError) as err:
            print(err)


    #time.sleep(0.5)
    #print("DIP: ",dip_detect())
    #time.sleep(0.5)
    #(438, 27, 39, 29)
    #print("LEDs: ",templatematch())

    #print()
