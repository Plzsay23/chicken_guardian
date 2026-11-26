"""M500 chassis serial protocol (shared by base_node and teleop_keyboard).

Confirmed on hardware 2026-10-07/08 (see ../README.md "알아낸 것" and the
root-level M500 reversing report). Two USB-C ports exist on the board,
"PC" and "ROS", exposing identical USB-serial chips (1a86:55d4) with
different serial numbers. Telemetry streams out of BOTH ports, but velocity
commands are only accepted on the "ROS" port.

Telemetry frame, robot -> PC, 24 bytes, ~19-20 Hz, big-endian:
    byte0    = 0x7B (header)
    byte1    = stop flag
    byte2-7  = vx, vy, wz  (int16, /1000 -> m/s, rad/s)
    byte8-13 = ax, ay, az  (int16, /1671.84 -> m/s^2)
    byte14-19= gx, gy, gz  (int16, *0.00026644 -> rad/s)
    byte20-21= battery voltage (uint16, mV)
    byte22   = XOR(byte0..21)
    byte23   = 0x7D (tail)

Command frame, PC -> robot, 11 bytes, confirmed working (REP-103 signs,
no inversion needed: +vx=forward, +wz=CCW from above):
    [0x7B, 0x00, 0x00, vx_hi, vx_lo, vy_hi, vy_lo, wz_hi, wz_lo, XOR(byte0..8), 0x7D]
    vx/vy/wz are int16 big-endian, x1000. build_cmd_frame() takes real-world
    rad/s for wz and internally applies WZ_COMPENSATION before encoding - see
    that constant's comment (the chassis only achieves ~43% of a commanded wz,
    confirmed linear across wz=0.3..3.0, so build_cmd_frame corrects for it).
"""

import struct

FRAME_LEN = 24
FRAME_START = 0x7B
FRAME_END = 0x7D

ACCEL_SCALE = 1671.84   # raw / ACCEL_SCALE -> m/s^2
GYRO_SCALE = 0.00026644  # raw * GYRO_SCALE -> rad/s


def xor_checksum(data: bytes) -> int:
    x = 0
    for b in data:
        x ^= b
    return x


def _s16(hi: int, lo: int) -> int:
    return struct.unpack(">h", bytes([hi, lo]))[0]


def decode_telemetry(buf: bytes):
    """Return a decoded dict if buf is a valid 24-byte telemetry frame, else None."""
    if len(buf) != FRAME_LEN:
        return None
    if buf[0] != FRAME_START or buf[23] != FRAME_END:
        return None
    if xor_checksum(buf[0:22]) != buf[22]:
        return None

    vx = _s16(buf[2], buf[3]) / 1000.0
    vy = _s16(buf[4], buf[5]) / 1000.0
    wz = _s16(buf[6], buf[7]) / 1000.0
    ax = _s16(buf[8], buf[9]) / ACCEL_SCALE
    ay = _s16(buf[10], buf[11]) / ACCEL_SCALE
    az = _s16(buf[12], buf[13]) / ACCEL_SCALE
    gx = _s16(buf[14], buf[15]) * GYRO_SCALE
    gy = _s16(buf[16], buf[17]) * GYRO_SCALE
    gz = _s16(buf[18], buf[19]) * GYRO_SCALE
    batt_mv = struct.unpack(">H", bytes([buf[20], buf[21]]))[0]

    return {
        "stop_flag": buf[1],
        "vx": vx, "vy": vy, "wz": wz,
        "ax": ax, "ay": ay, "az": az,
        "gx": gx, "gy": gy, "gz": gz,
        "batt_v": batt_mv / 1000.0,
    }


def extract_frames(buf: bytearray):
    """Scan buf for complete valid telemetry frames.

    Returns (list_of_decoded_dicts, remaining_bytes). Consumed bytes (including
    any garbage skipped before a valid frame) are dropped; remaining_bytes holds
    a possible partial frame at the tail to be completed by the next read.
    """
    decoded = []
    i = 0
    n = len(buf)
    while i < n:
        if buf[i] != FRAME_START:
            i += 1
            continue
        if i + FRAME_LEN > n:
            break  # incomplete frame at the tail, wait for more bytes
        candidate = bytes(buf[i:i + FRAME_LEN])
        d = decode_telemetry(candidate)
        if d:
            decoded.append(d)
            i += FRAME_LEN
        else:
            i += 1
    return decoded, buf[i:]


def _s16_bytes(v: float) -> bytes:
    iv = int(round(v * 1000))
    iv = max(-32768, min(32767, iv))
    return struct.pack(">h", iv)


# Measured 2026-10-08 (base/README.md "wz 명령-피드백 비율 스윕 테스트"): commanding
# wz in this frame yields only ~41.9-48% of that as actual chassis angular velocity,
# consistently across wz=0.3..3.0 (10x range, ratio does not drop at higher values -
# rules out torque/friction saturation, points to a linear scale mismatch instead).
# Mean ratio ~=0.434, so we pre-multiply by its inverse here so callers can treat
# wz in build_cmd_frame as real-world rad/s. vx/vy are NOT affected - they were
# independently verified accurate (odom distance test matched measured tape distance
# to ~1mm).
WZ_COMPENSATION = 1.0 / 0.434  # ~= 2.304


def build_cmd_frame(vx: float, vy: float, wz: float) -> bytes:
    """11-byte command frame, confirmed working on the "ROS" port.

    wz is the real-world desired angular velocity (rad/s); it is internally
    scaled by WZ_COMPENSATION before encoding to correct for the chassis's
    measured ~43% command-to-actual ratio. vx/vy are encoded as-is.
    """
    wz = wz * WZ_COMPENSATION
    frame = bytearray(11)
    frame[0] = 0x7B
    frame[1] = 0x00
    frame[2] = 0x00
    frame[3:5] = _s16_bytes(vx)
    frame[5:7] = _s16_bytes(vy)
    frame[7:9] = _s16_bytes(wz)
    frame[9] = xor_checksum(bytes(frame[0:9]))
    frame[10] = 0x7D
    return bytes(frame)
