#!/usr/bin/env python3
"""ROS 없이 라이트를 바로 켜고 끄는 시험용 스크립트 (light_node 와 동시에 쓰지 말 것).

    python3 ~/chicken/base/tools/light.py on       # 켜고 Ctrl+C 할 때까지 유지
    python3 ~/chicken/base/tools/light.py off
    python3 ~/chicken/base/tools/light.py blink    # 1초 간격 5번
옵션: --pin N (기본 7, 40핀 BOARD 번호)
"""
import argparse
import time

import Jetson.GPIO as GPIO

ap = argparse.ArgumentParser()
ap.add_argument("cmd", choices=["on", "off", "blink"])
ap.add_argument("--pin", type=int, default=7)
a = ap.parse_args()

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)
GPIO.setup(a.pin, GPIO.OUT, initial=GPIO.LOW)
try:
    if a.cmd == "on":
        GPIO.output(a.pin, GPIO.HIGH)
        print(f"pin {a.pin} HIGH — 켜짐 유지 중, Ctrl+C 로 끄고 종료")
        while True:
            time.sleep(1)
    elif a.cmd == "blink":
        for _ in range(5):
            GPIO.output(a.pin, GPIO.HIGH)
            print("ON")
            time.sleep(1)
            GPIO.output(a.pin, GPIO.LOW)
            print("OFF")
            time.sleep(1)
    else:
        print(f"pin {a.pin} LOW — 꺼짐")
except KeyboardInterrupt:
    pass
finally:
    GPIO.output(a.pin, GPIO.LOW)
    GPIO.cleanup()
