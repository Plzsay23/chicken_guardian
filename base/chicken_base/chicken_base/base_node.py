#!/usr/bin/env python3
"""chicken_base base_node: M500 chassis serial <-> ROS 2 bridge.

Subscribes /cmd_vel (geometry_msgs/Twist), publishes /odom (nav_msgs/Odometry,
no TF - see INTERFACES.md), /imu/data_raw (sensor_msgs/Imu), /battery
(sensor_msgs/BatteryState). See protocol.py for the wire format.

Safety:
  - Must be pointed at the board's "ROS" USB-C port (see protocol.py docstring).
  - Port opened with `stty -hupcl` + dtr=False/rts=False to avoid resetting the
    STM32 board via DTR/RTS toggling.
  - Velocity commands are clamped to max_vx/max_vy/max_wz params regardless of
    what /cmd_vel publishes.
  - Watchdog: zero velocity is sent if no /cmd_vel arrives within cmd_timeout_s.
  - On shutdown, zero velocity is sent several times before closing the port.
"""

import math
import subprocess
import time

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu, BatteryState
from std_srvs.srv import Trigger

from chicken_base.protocol import build_cmd_frame, extract_frames

try:
    import serial
except ImportError:
    serial = None

# Measured noise (base/README.md "알아낸 것" / "오돔 정확도 검증"), 2026-10-08:
#   gyro stationary std  ~= 0.0004 rad/s  -> variance ~= 1.6e-7
#   accel stationary std ~= 0.011 m/s^2   -> variance ~= 1.21e-4
#   vx steady-state std  ~= 0.0254 m/s    -> variance ~= 6.4e-4 (measured driving vx=0.15)
#   wz steady-state std  ~= 0.02 rad/s    -> variance ~= 4e-4   (measured driving wz=0.3)
#   vy is mechanically ~0 (no lateral motion) - small nonzero placeholder for
#   numerical stability only, not a real measurement.
GYRO_VARIANCE = 1.6e-7
ACCEL_VARIANCE = 1.21e-4
VX_VARIANCE = 6.4e-4
VY_VARIANCE = 1e-6
WZ_VARIANCE = 4e-4


def diag6(vx, vy, vz, wx, wy, wz):
    """6x6 row-major covariance with only the diagonal set (off-diagonal 0)."""
    m = [0.0] * 36
    m[0], m[7], m[14], m[21], m[28], m[35] = vx, vy, vz, wx, wy, wz
    return m


def diag3(a, b, c):
    """3x3 row-major covariance with only the diagonal set (off-diagonal 0)."""
    m = [0.0] * 9
    m[0], m[4], m[8] = a, b, c
    return m


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


class BaseNode(Node):
    def __init__(self):
        super().__init__('base_node')

        # /dev/base is the fixed udev symlink for this board's "ROS" port
        # (99-chicken-serial.rules, keyed on serial 5C8D079806). Use this, not
        # a raw /dev/ttyACM* path which can change across replugs/reboots.
        self.declare_parameter('port', '/dev/base')
        self.declare_parameter('baud', 115200)
        self.declare_parameter('rate_hz', 20.0)
        self.declare_parameter('cmd_timeout_s', 0.5)
        self.declare_parameter('max_vx', 0.3)
        self.declare_parameter('max_vy', 0.3)
        self.declare_parameter('max_wz', 1.0)
        self.declare_parameter('odom_frame_id', 'odom')
        self.declare_parameter('base_frame_id', 'base_link')
        self.declare_parameter('imu_frame_id', 'imu_link')

        self.port = self.get_parameter('port').value
        self.baud = self.get_parameter('baud').value
        self.rate_hz = self.get_parameter('rate_hz').value
        self.cmd_timeout_s = self.get_parameter('cmd_timeout_s').value
        self.max_vx = self.get_parameter('max_vx').value
        self.max_vy = self.get_parameter('max_vy').value
        self.max_wz = self.get_parameter('max_wz').value
        self.odom_frame_id = self.get_parameter('odom_frame_id').value
        self.base_frame_id = self.get_parameter('base_frame_id').value
        self.imu_frame_id = self.get_parameter('imu_frame_id').value

        if serial is None:
            raise RuntimeError('pyserial not installed (apt install python3-serial)')

        self._open_serial()

        self.target_vx = 0.0
        self.target_vy = 0.0
        self.target_wz = 0.0
        self.last_cmd_time = self.get_clock().now()
        self.rx_buf = bytearray()

        # dead-reckoning odometry state (board gives velocities only, no pose)
        self.odom_x = 0.0
        self.odom_y = 0.0
        self.odom_theta = 0.0
        self.last_telemetry_time = None

        self.odom_pub = self.create_publisher(Odometry, 'odom', 10)
        self.imu_pub = self.create_publisher(Imu, 'imu/data_raw', 10)
        self.battery_pub = self.create_publisher(BatteryState, 'battery', 10)
        self.cmd_sub = self.create_subscription(Twist, 'cmd_vel', self.on_cmd_vel, 10)
        self.reset_odom_srv = self.create_service(
            Trigger, 'reset_odom', self.on_reset_odom)

        self.timer = self.create_timer(1.0 / self.rate_hz, self.on_timer)
        self.get_logger().info(
            f'base_node up: port={self.port} baud={self.baud} '
            f'caps=(vx<={self.max_vx}, vy<={self.max_vy}, wz<={self.max_wz})')

    def _open_serial(self):
        try:
            subprocess.run(['stty', '-F', self.port, '-hupcl'], check=True,
                            capture_output=True, text=True)
        except FileNotFoundError:
            pass
        except subprocess.CalledProcessError as e:
            self.get_logger().warning(f'stty -hupcl failed: {e.stderr.strip()}')

        self.ser = serial.Serial()
        self.ser.port = self.port
        self.ser.baudrate = self.baud
        self.ser.bytesize = serial.EIGHTBITS
        self.ser.parity = serial.PARITY_NONE
        self.ser.stopbits = serial.STOPBITS_ONE
        self.ser.timeout = 0.0
        self.ser.dtr = False
        self.ser.rts = False
        self.ser.open()
        self.ser.dtr = False
        self.ser.rts = False

    def on_cmd_vel(self, msg: Twist):
        self.target_vx = clamp(msg.linear.x, -self.max_vx, self.max_vx)
        self.target_vy = clamp(msg.linear.y, -self.max_vy, self.max_vy)
        self.target_wz = clamp(msg.angular.z, -self.max_wz, self.max_wz)
        self.last_cmd_time = self.get_clock().now()

    def on_reset_odom(self, request, response):
        self.odom_x = 0.0
        self.odom_y = 0.0
        self.odom_theta = 0.0
        self.get_logger().info('reset_odom: odom reset to (0, 0, 0)')
        response.success = True
        response.message = 'odom reset to (0, 0, 0)'
        return response

    def on_timer(self):
        elapsed = (self.get_clock().now() - self.last_cmd_time).nanoseconds / 1e9
        if elapsed > self.cmd_timeout_s:
            vx = vy = wz = 0.0
        else:
            vx, vy, wz = self.target_vx, self.target_vy, self.target_wz

        try:
            self.ser.write(build_cmd_frame(vx, vy, wz))
        except serial.SerialException as e:
            self.get_logger().error(f'serial write failed: {e}')
            return

        try:
            chunk = self.ser.read(4096)
        except serial.SerialException as e:
            self.get_logger().error(f'serial read failed: {e}')
            return

        if chunk:
            self.rx_buf.extend(chunk)
        if len(self.rx_buf) >= 24:
            frames, remaining = extract_frames(self.rx_buf)
            self.rx_buf = bytearray(remaining)
            for d in frames:
                self._publish_telemetry(d)

    def _publish_telemetry(self, d: dict):
        now = self.get_clock().now()
        stamp = now.to_msg()

        if self.last_telemetry_time is not None:
            dt = (now - self.last_telemetry_time).nanoseconds / 1e9
            if 0.0 < dt < 1.0:
                vx, vy, wz = d['vx'], d['vy'], d['wz']
                c, s = math.cos(self.odom_theta), math.sin(self.odom_theta)
                self.odom_x += (vx * c - vy * s) * dt
                self.odom_y += (vx * s + vy * c) * dt
                self.odom_theta += wz * dt
        self.last_telemetry_time = now

        odom = Odometry()
        odom.header.stamp = stamp
        odom.header.frame_id = self.odom_frame_id
        odom.child_frame_id = self.base_frame_id
        odom.pose.pose.position.x = self.odom_x
        odom.pose.pose.position.y = self.odom_y
        odom.pose.pose.orientation.z = math.sin(self.odom_theta / 2.0)
        odom.pose.pose.orientation.w = math.cos(self.odom_theta / 2.0)
        odom.twist.twist.linear.x = d['vx']
        odom.twist.twist.linear.y = d['vy']
        odom.twist.twist.angular.z = d['wz']
        odom.twist.covariance = diag6(VX_VARIANCE, VY_VARIANCE, 0.0, 0.0, 0.0, WZ_VARIANCE)
        self.odom_pub.publish(odom)

        imu = Imu()
        imu.header.stamp = stamp
        imu.header.frame_id = self.imu_frame_id
        imu.orientation_covariance[0] = -1.0  # orientation not provided by this board
        imu.linear_acceleration.x = d['ax']
        imu.linear_acceleration.y = d['ay']
        imu.linear_acceleration.z = d['az']
        imu.linear_acceleration_covariance = diag3(
            ACCEL_VARIANCE, ACCEL_VARIANCE, ACCEL_VARIANCE)
        imu.angular_velocity.x = d['gx']
        imu.angular_velocity.y = d['gy']
        imu.angular_velocity.z = d['gz']
        imu.angular_velocity_covariance = diag3(
            GYRO_VARIANCE, GYRO_VARIANCE, GYRO_VARIANCE)
        self.imu_pub.publish(imu)

        batt = BatteryState()
        batt.header.stamp = stamp
        batt.voltage = float(d['batt_v'])
        batt.present = True
        self.battery_pub.publish(batt)

    def shutdown(self):
        self.get_logger().info('shutting down: sending zero velocity')
        zero = build_cmd_frame(0.0, 0.0, 0.0)
        try:
            for _ in range(10):
                self.ser.write(zero)
                time.sleep(0.05)
        except Exception:
            pass
        try:
            self.ser.dtr = False
            self.ser.rts = False
            self.ser.close()
        except Exception:
            pass


def main():
    rclpy.init()
    node = BaseNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
