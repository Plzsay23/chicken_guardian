#!/usr/bin/env python3
"""명령 프레임의 예비 바이트(byte1, byte2)로 라이트가 제어되는지 시험한다.

속도는 항상 0 으로 보낸다. 그래도 펌웨어가 예비 바이트를 다른 뜻으로 쓸 수 있으니 바퀴를 띄우고 한다.
base_node 를 끄고 실행한다(같은 포트를 두 프로세스가 쓰면 프레임이 섞인다). 라이트는 보드에 꽂아 둔다.
    python3 ~/chicken/base/tools/cmd_byte_probe.py [포트]
값마다 3초 동안 10 Hz 로 보낸 뒤 Enter 를 기다린다. 라이트가 바뀌면 y 를 입력해 기록한다. q 로 중단.
"""
import sys
import time

import serial

port = sys.argv[1] if len(sys.argv) > 1 else "/dev/base"
s = serial.Serial(port, 115200, timeout=0.1)


def frame(b1, b2):
    f = bytes([0x7B, b1, b2, 0, 0, 0, 0, 0, 0])  # vx = vy = wz = 0
    x = 0
    for b in f:
        x ^= b
    return f + bytes([x, 0x7D])


def send(b1, b2, sec):
    t = time.time()
    while time.time() - t < sec:
        s.write(frame(b1, b2))
        s.reset_input_buffer()
        time.sleep(0.1)


values = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0xFF]
cases = [(v, 0) for v in values] + [(0, v) for v in values]
hits = []
print("바퀴를 띄웠는지, base_node 를 껐는지 확인하세요. Enter 로 시작")
input()
try:
    for b1, b2 in cases:
        print(f"byte1=0x{b1:02X} byte2=0x{b2:02X} 보내는 중 (3초)...", flush=True)
        send(b1, b2, 3.0)
        send(0, 0, 0.5)  # 원래대로
        ans = input("  라이트가 바뀌었나요? [Enter=아니오 / y=예 / q=중단] ").strip().lower()
        if ans == "q":
            break
        if ans == "y":
            hits.append((b1, b2))
finally:
    send(0, 0, 0.5)
    s.close()
print("반응한 값:", ", ".join(f"byte1=0x{a:02X} byte2=0x{b:02X}" for a, b in hits) or "없음")
