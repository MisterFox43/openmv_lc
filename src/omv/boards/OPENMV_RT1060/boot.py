import machine, time
led = machine.LED("LED_RED")
while (True):
   led.on()
   time.sleep_ms(550)
   led.off()
   time.sleep_ms(400)
   led.on()
   time.sleep_ms(550)
   led.off()
   time.sleep_ms(600)
