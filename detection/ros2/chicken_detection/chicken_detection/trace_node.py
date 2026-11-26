"""ROS 2 node: tiny-trace detection on the patrol robot (FR-04, FR-05, FR-10).

patrol  : timer at patrol_hz runs the light sliced detector on the newest camera frame,
          publishes /traces/detections and /traces/candidate (Bool, latched-ish) so the
          navigation side can stop the robot.
confirm : service /traces/confirm (std_srvs/Trigger), called after the robot has stopped.
          Runs the full-overlap + TTA detector, saves frame + JSON with the robot pose
          (TF map->base_link) under record_dir, publishes /traces/confirmed.

The detection code itself is the shared `traces` package from the detection/ folder
(set traces_root), so the robot runs exactly what was evaluated on the PC.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from std_msgs.msg import Bool
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformListener
from vision_msgs.msg import Detection2D, Detection2DArray, ObjectHypothesisWithPose


class TraceNode(Node):
    def __init__(self):
        super().__init__("trace_detector")
        p = self.declare_parameter
        traces_root = p("traces_root", str(Path.home() / "chicken" / "detection")).value
        sys.path.insert(0, traces_root)
        from traces import load_cfg
        from traces.sliced import SlicedDetector

        self.cfg = load_cfg(p("cfg", str(Path(traces_root) / "configs" / "traces.yaml")).value)
        self.names = self.cfg["classes"]
        weights = p("weights", str(Path(traces_root) / "weights" / "best.engine")).value
        self.image_topic = p("image_topic", "/camera/front/image_raw").value
        self.patrol_hz = float(p("patrol_hz", 2.0).value)
        self.record_dir = Path(p("record_dir", str(Path.home() / "chicken" / "records" / "traces")).value)
        self.map_frame = p("map_frame", "map").value
        self.base_frame = p("base_frame", "base_link").value
        self.alarm_cls = int(p("alarm_class", 0).value)  # class that triggers a stop (rodent_dropping)
        self.max_frame_age = float(p("max_frame_age_s", 1.0).value)

        self.get_logger().info(f"loading {weights}")
        self.det = SlicedDetector(weights, self.cfg["tile"]["size"], names=self.names)
        self.bridge = CvBridge()
        self.latest = None  # (msg header, bgr frame, receive time)

        self.tf_buf = Buffer()
        self.tf_listener = TransformListener(self.tf_buf, self)
        self.create_subscription(Image, self.image_topic, self.on_image, qos_profile_sensor_data)
        self.pub_det = self.create_publisher(Detection2DArray, "/traces/detections", 10)
        self.pub_conf = self.create_publisher(Detection2DArray, "/traces/confirmed", 10)
        self.pub_cand = self.create_publisher(Bool, "/traces/candidate", 10)
        self.create_service(Trigger, "/traces/confirm", self.on_confirm)
        self.create_timer(1.0 / self.patrol_hz, self.on_patrol)
        self.get_logger().info(f"listening on {self.image_topic}, patrol {self.patrol_hz} Hz")

    def on_image(self, msg):
        self.latest = (msg.header, self.bridge.imgmsg_to_cv2(msg, "bgr8"), time.monotonic())

    def _fresh_frame(self):
        if self.latest is None or time.monotonic() - self.latest[2] > self.max_frame_age:
            return None
        return self.latest

    def _run(self, frame, mode):
        m = self.cfg["infer"][mode]
        return self.det(frame, conf=m["conf"], overlap=m["overlap"], scale=m["scale"], tta=m["tta"],
                        iou_merge=self.cfg["infer"]["iou_merge"]), m["conf"]

    def _to_msg(self, header, dets):
        arr = Detection2DArray()
        arr.header = header
        for b, s, c in zip(dets.boxes, dets.scores, dets.classes):
            d = Detection2D()
            d.header = header
            d.bbox.center.position.x = float((b[0] + b[2]) / 2)
            d.bbox.center.position.y = float((b[1] + b[3]) / 2)
            d.bbox.size_x = float(b[2] - b[0])
            d.bbox.size_y = float(b[3] - b[1])
            h = ObjectHypothesisWithPose()
            h.hypothesis.class_id = self.names[int(c)]
            h.hypothesis.score = float(s)
            d.results.append(h)
            arr.detections.append(d)
        return arr

    def on_patrol(self):
        f = self._fresh_frame()
        if f is None:
            return
        header, frame, _ = f
        dets, conf = self._run(frame, "patrol")
        self.pub_det.publish(self._to_msg(header, dets))
        hit = bool(((dets.classes == self.alarm_cls) & (dets.scores >= conf)).any())
        self.pub_cand.publish(Bool(data=hit))

    def _pose(self):
        try:
            t = self.tf_buf.lookup_transform(self.map_frame, self.base_frame, rclpy.time.Time())
            tr, q = t.transform.translation, t.transform.rotation
            return {"frame": self.map_frame, "x": tr.x, "y": tr.y, "qz": q.z, "qw": q.w}
        except Exception as e:  # no map yet (teleop only) - still record the detection
            return {"error": str(e)}

    def on_confirm(self, req, res):
        f = self._fresh_frame()
        if f is None:
            res.success, res.message = False, "no fresh camera frame"
            return res
        header, frame, _ = f
        t0 = time.perf_counter()
        dets, _ = self._run(frame, "confirm")
        ms = (time.perf_counter() - t0) * 1000
        self.pub_conf.publish(self._to_msg(header, dets))

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        self.record_dir.mkdir(parents=True, exist_ok=True)
        import cv2
        from traces.sliced import draw

        cv2.imwrite(str(self.record_dir / f"{stamp}.jpg"), frame)  # raw frame = future training data
        cv2.imwrite(str(self.record_dir / f"{stamp}_vis.jpg"), draw(frame, dets, self.names))
        counts = {n: int((dets.classes == i).sum()) for i, n in enumerate(self.names)}
        rec = {"time": stamp, "pose": self._pose(), "counts": counts, "ms": round(ms, 1),
               "detections": dets.to_list(self.names)}
        (self.record_dir / f"{stamp}.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        res.success = True
        res.message = json.dumps({"counts": counts, "record": stamp}, ensure_ascii=False)
        self.get_logger().info(f"confirm: {counts} in {ms:.0f} ms -> {stamp}")
        return res


def main():
    rclpy.init()
    node = TraceNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
