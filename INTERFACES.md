# 파트 간 인터페이스

파트끼리의 약속은 여기에만 적는다. 바꾸기 전에 이 표부터 고친다. 상태: `계획` → `구현` → `검증`.

## 토픽

| 토픽 | 타입 | 발행 파트 | 구독 파트 | 주기 | 프레임 | 상태 |
|---|---|---|---|---|---|---|
| `/cmd_vel` | geometry_msgs/Twist | navigation, 텔레옵 | base | – | base_link | 계획 |
| `/odom` | nav_msgs/Odometry | base | slam | 20 Hz | odom → base_link | 구현 |
| `/imu/data_raw` | sensor_msgs/Imu | base | slam | 20 Hz | imu_link | 구현 |
| `/light` | std_msgs/Bool (+ 서비스 `/set_light` SetBool, 상태 `/light/state`) | 누구나 | base (light_node) | – | – | 구현 |
| `/battery` | sensor_msgs/BatteryState | base | integration | 20 Hz | – | 계획 |
| `/scan` | sensor_msgs/LaserScan | slam (라이다 드라이버) | slam | 8.4 Hz | laser_frame | 구현 |
| `/odometry/filtered` | nav_msgs/Odometry | slam (EKF) | navigation | 30 Hz | odom → base_link | 구현 |
| `/map` | nav_msgs/OccupancyGrid | slam | navigation | 1 Hz | map | 구현 |

## TF

| 변환 | 담당 파트 | 비고 |
|---|---|---|
| `map → odom` | slam | |
| `odom → base_link` | slam (EKF, chicken_slam ekf.yaml) — 구현 | base 는 `/odom` 메시지만 내고 TF 는 발행하지 않는다 — EKF 와 중복 방지 |
| `base_link → 센서들` | integration (URDF) | 임시: chicken_slam 이 base_link→laser_frame(x 0.13, z 0.06)·imu_link(항등) 발행. base_link 원점 = 보드 IMU |

## 기타

- `ROS_DOMAIN_ID`: 미정 (기본 0)
