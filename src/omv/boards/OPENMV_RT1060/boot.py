
# main.py -- put your code here!"
import machine, time
led = machine.LED(\"LED_BLUE\")
while (True):
   led.on()
   time.sleep_ms(550)
   led.off()
   time.sleep_ms(400)
   led.on()
   time.sleep_ms(550)
   led.off()
   time.sleep_ms(600)

