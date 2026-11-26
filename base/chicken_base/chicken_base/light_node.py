"""chicken_base light_node: 로봇 라이트를 젯슨 GPIO 로 켜고 끈다.

배선 (base/README.md 참고): 라이트 주황(신호)선을 다이오드 OR 로 보드와 젯슨이 함께 구동한다.
리모컨이 켜 둔 상태면 젯슨이 끌 수 없다(OR 동작).

  - Subscribes /light (std_msgs/Bool): true=켜기, false=끄기
  - Service /set_light (std_srvs/SetBool): 같은 동작, 결과를 돌려준다
  - Publishes /light/state (std_msgs/Bool, latched): 젯슨이 내고 있는 출력값
  - 종료 시 핀을 LOW 로 내리고 해제한다(풀다운으로 꺼짐)
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import Bool
from std_srvs.srv import SetBool

try:
    import Jetson.GPIO as GPIO
except ImportError:  # Jetson 이 아닌 곳
    GPIO = None


class LightNode(Node):
    def __init__(self):
        super().__init__('light_node')
        self.declare_parameter('pin', 7)  # 40핀 헤더 BOARD 번호
        self.declare_parameter('initial_on', False)
        self.pin = int(self.get_parameter('pin').value)

        if GPIO is None:
            raise RuntimeError('Jetson.GPIO not available')
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(self.pin, GPIO.OUT, initial=GPIO.LOW)

        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.state_pub = self.create_publisher(Bool, 'light/state', latched)
        self.create_subscription(Bool, 'light', lambda m: self.set(m.data), 10)
        self.create_service(SetBool, 'set_light', self.on_set_light)

        self.set(bool(self.get_parameter('initial_on').value))
        self.get_logger().info(f'light on BOARD pin {self.pin} ready (/light, /set_light)')

    def set(self, on: bool):
        GPIO.output(self.pin, GPIO.HIGH if on else GPIO.LOW)
        self.state_pub.publish(Bool(data=on))
        self.get_logger().info(f'light {"ON" if on else "OFF"}')

    def on_set_light(self, req, res):
        self.set(req.data)
        res.success = True
        res.message = 'on' if req.data else 'off'
        return res

    def shutdown(self):
        try:
            GPIO.output(self.pin, GPIO.LOW)
            GPIO.cleanup(self.pin)
        except Exception:
            pass


def main():
    rclpy.init()
    node = LightNode()
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
