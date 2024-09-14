static const char fresh_main_py[] =
    "# main.py -- put your code here!\n"
    "import machine, time\n"
    "led = machine.LED(\"LED_BLUE\")\n"
    "while (True):\n"
    "   led.on()\n"
    "   time.sleep_ms(550)\n"
    "   led.off()\n"
    "   time.sleep_ms(400)\n"
    "   led.on()\n"
    "   time.sleep_ms(550)\n"
    "   led.off()\n"
    "   time.sleep_ms(600)\n"
;
