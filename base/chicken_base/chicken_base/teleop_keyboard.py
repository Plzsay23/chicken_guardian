#!/usr/bin/env python3
"""chicken_base teleop_keyboard: hold-to-move keyboard teleop, publishes /cmd_vel.

  - Moves only while a key is HELD; releasing it stops the robot.
  - Forward/backward arcs (turning while driving) have their own keys.
  - /cmd_vel is published continuously at publish_rate_hz, so base_node's
    cmd_timeout_s watchdog stops the robot if this node dies.
Verified on the real robot 2026-10-08 (release -> immediate stop confirmed).

Keys (hold):
    q  w  e      q/e : forward + turn left / right (arc)     w : forward
    a     d      a/d : rotate in place, CCW / CW
    z  s  c      z/c : backward + turn left / right (arc)    s : backward
  r / f : speed up / down        space / x : stop        CTRL-C : quit

The chassis has no steering: turning is done by the base board running the
left/right wheels at different speeds from the (vx, wz) it is sent.
z/c follow a car reversing with the wheel turned left/right: z ends up
backward-left (vx<0, wz<0), c backward-right (vx<0, wz>0).

Release detection: a terminal only sees key presses, never releases. A held
key produces autorepeat (first repeat after the OS delay, ~500 ms, then every
~30 ms), so "released" = no repeat arrived within hold_first_timeout_s (before
the first repeat) or hold_repeat_timeout_s (once repeats are flowing).

Run:
    ros2 run chicken_base teleop_keyboard

Per AGENTS.md section 3: only run this against the real robot after a human
has confirmed the wheels are off the ground / safe to move.
"""

import select
import sys
import termios
import time
import tty

import rclpy
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions
from geometry_msgs.msg import Twist

# key -> (x, th) direction multipliers; vx = x * speed, wz = th * turn
MOVE_BINDINGS = {
    'w': (1, 0), 'q': (1, 1), 'e': (1, -1),
    's': (-1, 0), 'z': (-1, -1), 'c': (-1, 1),
    'a': (0, 1), 'd': (0, -1),
}
MOVE_LABELS = {
    (0, 0): '정지', (1, 0): '전진', (-1, 0): '후진',
    (1, 1): '전진+좌', (1, -1): '전진+우', (-1, -1): '후진+좌', (-1, 1): '후진+우',
    (0, 1): '제자리 좌회전', (0, -1): '제자리 우회전',
}
STOP_KEYS = (' ', 'x')
POLL_S = 0.02
MPS_TO_KMH = 3.6
RAD_TO_DEG = 57.29578


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


class TeleopKeyboard(Node):
    def __init__(self):
        super().__init__('teleop_keyboard')
        self.declare_parameter('max_vx', 0.3)
        self.declare_parameter('max_wz', 1.0)
        self.declare_parameter('vx_step', 0.05)
        self.declare_parameter('wz_step', 0.1)
        self.declare_parameter('vx_min_step', 0.05)
        self.declare_parameter('wz_min_step', 0.1)
        self.declare_parameter('publish_rate_hz', 10.0)
        self.declare_parameter('hold_first_timeout_s', 0.6)
        self.declare_parameter('hold_repeat_timeout_s', 0.15)

        self.max_vx = self.get_parameter('max_vx').value
        self.max_wz = self.get_parameter('max_wz').value
        self.vx_step = self.get_parameter('vx_step').value
        self.wz_step = self.get_parameter('wz_step').value
        self.vx_min_step = self.get_parameter('vx_min_step').value
        self.wz_min_step = self.get_parameter('wz_min_step').value
        self.publish_rate_hz = self.get_parameter('publish_rate_hz').value
        self.hold_first_timeout_s = self.get_parameter('hold_first_timeout_s').value
        self.hold_repeat_timeout_s = self.get_parameter('hold_repeat_timeout_s').value

        self.pub = self.create_publisher(Twist, 'cmd_vel', 10)
        self.speed = self.vx_min_step * 2
        self.turn = self.wz_min_step * 2
        self.x = 0    # direction multiplier -1/0/+1, from the held key
        self.th = 0   # direction multiplier -1/0/+1
        self.held_key = None
        self.held_repeating = False
        self.last_key_time = 0.0

    def publish(self):
        vx = clamp(self.x * self.speed, -self.max_vx, self.max_vx)
        wz = clamp(self.th * self.turn, -self.max_wz, self.max_wz)
        msg = Twist()
        msg.linear.x = vx
        msg.angular.z = wz
        self.pub.publish(msg)
        label = MOVE_LABELS[(self.x, self.th)]
        print(f'\r[{label}] 명령 vx={vx:+.2f} m/s wz={wz:+.2f} rad/s | '
              f'설정 {self.speed:.2f} m/s({self.speed / self.max_vx:.0%}) '
              f'{self.turn:.2f} rad/s({self.turn / self.max_wz:.0%})\x1b[K', end='')
        sys.stdout.flush()

    def print_setting(self, what: str):
        """Log the speed setting on its own line (stdin is raw, so \\r\\n)."""
        notes = []
        if self.speed >= self.max_vx:
            notes.append('** 전진 최대 **')
        elif self.speed <= self.vx_min_step:
            notes.append('(전진 최소)')
        if self.turn >= self.max_wz:
            notes.append('** 회전 최대 **')
        elif self.turn <= self.wz_min_step:
            notes.append('(회전 최소)')
        note = ('  ' + ' '.join(notes)) if notes else ''
        print(f'\r\x1b[K{what}: 전진 {self.speed:.2f} m/s '
              f'({self.speed * MPS_TO_KMH:.2f} km/h, 최대 {self.max_vx:.2f}의 '
              f'{self.speed / self.max_vx:.0%}) / 회전 {self.turn:.2f} rad/s '
              f'({self.turn * RAD_TO_DEG:.0f}°/s, 최대 {self.max_wz:.2f}의 '
              f'{self.turn / self.max_wz:.0%}){note}\r\n', end='')

    def stop(self):
        self.x = 0
        self.th = 0
        self.held_key = None
        self.held_repeating = False

    def handle_key(self, key: str, now: float) -> bool:
        """Return False to quit. Returns True and changes state otherwise."""
        if key in MOVE_BINDINGS:
            # same key again = autorepeat from holding it; a new key = fresh press
            self.held_repeating = (key == self.held_key)
            self.held_key = key
            self.last_key_time = now
            self.x, self.th = MOVE_BINDINGS[key]
        elif key == 'r':
            self.speed = clamp(self.speed + self.vx_step, self.vx_min_step, self.max_vx)
            self.turn = clamp(self.turn + self.wz_step, self.wz_min_step, self.max_wz)
            self.print_setting('▲ 속도 업')
        elif key == 'f':
            self.speed = clamp(self.speed - self.vx_step, self.vx_min_step, self.max_vx)
            self.turn = clamp(self.turn - self.wz_step, self.wz_min_step, self.max_wz)
            self.print_setting('▼ 속도 다운')
        elif key in STOP_KEYS:
            self.stop()
        elif key == '\x03':  # Ctrl-C
            return False
        return True

    def check_release(self, now: float) -> bool:
        """Stop if the held key's autorepeat has gone quiet. Return True if it stopped."""
        if self.held_key is None:
            return False
        timeout = self.hold_repeat_timeout_s if self.held_repeating else self.hold_first_timeout_s
        if now - self.last_key_time > timeout:
            self.stop()
            return True
        return False


def get_key(timeout):
    """Return one key, or '' if none arrives within timeout seconds (stdin already raw)."""
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    return sys.stdin.read(1) if ready else ''


def main():
    # No rclpy SIGINT handler: a signal-triggered Ctrl-C then still has a live
    # context, so the final zero Twist in `finally` actually gets published.
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = TeleopKeyboard()
    print(f"""
chicken_base 키보드 텔레옵 [누르고 있는 동안만 이동]
   q  w  e     w/s : 전진/후진        q/e : 전진하며 좌/우 회전
   a     d     a/d : 제자리 좌/우 회전
   z  s  c     z/c : 후진하며 좌/우 회전 (자동차 후진처럼 왼쪽뒤/오른쪽뒤로)
  r/f : 속도 업/다운   space/x : 정지   Ctrl-C : 종료
  키에서 손을 떼면 정지 (처음 누른 직후 최대 {node.hold_first_timeout_s:.1f}s, 꾹 누르는 중엔 {node.hold_repeat_timeout_s:.2f}s 안에)
  속도 한도: |vx|<={node.max_vx:.2f} m/s, |wz|<={node.max_wz:.2f} rad/s (max_vx/max_wz 파라미터)
  r/f 한 번에: 전진 ±{node.vx_step:.2f} m/s, 회전 ±{node.wz_step:.2f} rad/s
""")
    node.print_setting('시작 설정')
    settings = termios.tcgetattr(sys.stdin)
    try:
        # raw for the whole session (not per key), so no keystroke falls between modes
        tty.setraw(sys.stdin.fileno())
        period = 1.0 / node.publish_rate_hz
        next_pub = 0.0
        while rclpy.ok():
            key = get_key(POLL_S)
            now = time.monotonic()
            before = (node.x, node.th)
            if not node.handle_key(key, now):
                break
            node.check_release(now)
            # publish on the rate tick, and immediately when the motion changes
            if now >= next_pub or (node.x, node.th) != before:
                node.publish()
                next_pub = now + period
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)
        node.stop()
        for _ in range(3):  # a few zeros so a single dropped message can't leave it moving
            node.publish()
        print()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
