#!/usr/bin/env python3
"""USB DAC(MT979) → LM386 → 피에조 시험음. 기본은 사람이 들을 수 있는 소리만 낸다.

    python3 ~/chicken/deterrence/tools/tone.py                 # 500 → 1000 → 2000 → 4000 Hz, 각 1초
    python3 ~/chicken/deterrence/tools/tone.py --freq 2000 --sec 3
    python3 ~/chicken/deterrence/tools/tone.py --vol 0.1       # 작게 (0~1, 기본 0.3)
앰프 입력은 DAC 의 L 채널만 쓴다(MT350 L → 앰프 IN). 15 kHz 넘는 주파수는 --allow-ultrasonic 없이는 거부한다.
"""
import argparse
import math
import struct
import subprocess
import sys

CARD = "CX31993MAX97220"  # aplay -l 의 카드 이름 (번호는 바뀔 수 있어 이름으로 지정)
RATE = 48000

ap = argparse.ArgumentParser()
ap.add_argument("--freq", type=float, nargs="*", default=[500, 1000, 2000, 4000])
ap.add_argument("--sec", type=float, default=1.0)
ap.add_argument("--vol", type=float, default=0.3)
ap.add_argument("--allow-ultrasonic", action="store_true")
a = ap.parse_args()

if not 0 < a.vol <= 1:
    sys.exit("--vol 은 0~1")
if any(f > 15000 for f in a.freq) and not a.allow_ultrasonic:
    sys.exit("15 kHz 초과는 --allow-ultrasonic 이 필요합니다")

frames = bytearray()
fade = int(RATE * 0.01)  # 10 ms 페이드 — 시작·끝 딸깍 소리 방지
for f in a.freq:
    n = int(RATE * a.sec)
    for i in range(n):
        env = min(1.0, i / fade, (n - 1 - i) / fade)
        v = int(32767 * a.vol * env * math.sin(2 * math.pi * f * i / RATE))
        frames += struct.pack("<hh", v, 0)  # L = 신호, R = 무음
    frames += bytes(4 * int(RATE * 0.2))  # 음 사이 0.2 초 쉼
    print(f"{f:.0f} Hz {a.sec:.1f}s")

cmd = ["aplay", "-q", "-D", f"dac", "-f", "S16_LE", "-c", "2", "-r", str(RATE)]
subprocess.run(cmd, input=bytes(frames), check=True)
