#!/usr/bin/env python3
"""보드가 보내는 원시 프레임을 감시해 바뀌는 값을 찍는다 (라이트 등 숨은 상태 찾기용).

base_node 를 끄고 실행한다 — 같은 포트를 두 프로세스가 읽으면 바이트가 나뉜다.
    python3 ~/chicken/base/tools/watch_frames.py [포트] [로그파일]
출력:
  - stop 플래그(byte1)가 바뀌면 즉시 한 줄
  - 24바이트 텔레메트리가 아닌 낯선 바이트/프레임이 오면 hex 로 한 줄
  - 1초마다 상태 한 줄 (프레임 수, byte1, 전압)
원시 바이트는 로그파일(기본 /tmp/frames_raw.bin)에 그대로 저장한다. Ctrl+C 로 끝.
"""
import struct
import sys
import time

import serial

port = sys.argv[1] if len(sys.argv) > 1 else "/dev/base"
log_path = sys.argv[2] if len(sys.argv) > 2 else "/tmp/frames_raw.bin"

s = serial.Serial(port, 115200, timeout=0.1)
log = open(log_path, "wb")
buf = b""
t0 = time.time()
last_b1 = None
n = 0
last_print = 0.0
volt = 0.0


def ts():
    return "%7.2fs" % (time.time() - t0)


print(f"{port} 감시 시작 — 라이트를 켰다 껐다 해보세요. Ctrl+C 로 종료")
try:
    while True:
        chunk = s.read(512)
        if chunk:
            log.write(chunk)
            buf += chunk
        while len(buf) >= 24:
            if buf[0] == 0x7B and buf[23] == 0x7D:
                x = 0
                for b in buf[:22]:
                    x ^= b
                if x == buf[22]:
                    f = buf[:24]
                    buf = buf[24:]
                    n += 1
                    volt = struct.unpack(">H", f[20:22])[0] / 1000
                    if f[1] != last_b1:
                        print(f"{ts()}  byte1(stop) {last_b1} -> {f[1]}  (0x{f[1]:02X}, 0b{f[1]:08b})")
                        last_b1 = f[1]
                    continue
            # 텔레메트리 형식이 아닌 바이트: 다음 0x7B 까지 묶어서 보여준다
            nxt = buf.find(b"\x7b", 1)
            junk = buf[: nxt if nxt > 0 else len(buf)]
            buf = buf[len(junk):]
            print(f"{ts()}  낯선 바이트 {len(junk)}B: {junk.hex( )}")
        if time.time() - last_print >= 1.0:
            print(f"{ts()}  프레임 {n:5d}  byte1={last_b1}  전압={volt:.2f}V")
            last_print = time.time()
except KeyboardInterrupt:
    pass
finally:
    log.close()
    print(f"\n끝. 원시 바이트 저장: {log_path}")
