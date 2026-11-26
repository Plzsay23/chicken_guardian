# slam — SLAM

## 상태
- 라이다 드라이버 + slam_toolbox 제자리 맵핑 동작 확인(2026-10-08). /scan 8.4 Hz, /map 생성, map→base_link TF 정상.
- 2026-10-08 EKF(robot_localization) 연동: /odom(vx,vy) + /imu/data_raw(vyaw) → odom→base_link. 정지 상태에서 TF 체인 map→odom→base_link 확인. **실제 주행 맵핑은 아직 안 해봄.**

## 실행 방법
```bash
cd ~/chicken && source /opt/ros/jazzy/setup.bash
# 최초 1회: 외부 드라이버 소스 받기 (저장소에는 안 올라간다 — .gitignore)
mkdir -p slam/third_party && cd slam/third_party
git clone https://github.com/YDLIDAR/YDLidar-SDK.git          && git -C YDLidar-SDK          checkout 42a82ed
git clone -b humble https://github.com/YDLIDAR/ydlidar_ros2_driver.git && git -C ydlidar_ros2_driver checkout 4ef70d3
cd ~/chicken
# 최초 1회: SDK 를 먼저 빌드해야 드라이버가 찾는다(드라이버 package.xml 에 의존성 선언이 없음)
colcon build --packages-select ydlidar_sdk --cmake-args -DCMAKE_BUILD_TYPE=Release
source install/setup.bash
colcon build --symlink-install --packages-select ydlidar_ros2_driver chicken_slam --cmake-args -DCMAKE_BUILD_TYPE=Release -DCMAKE_EXE_LINKER_FLAGS=-L$HOME/chicken/install/ydlidar_sdk/lib
source install/setup.bash
ros2 launch chicken_base base.launch.py               # 터미널 1 — base_node 는 하나만!
ros2 launch chicken_slam mapping.launch.py            # 터미널 2 — odom:=fake 면 base 없이 제자리 테스트
# 원격 보기: Foxglove(app.foxglove.dev 또는 데스크톱 앱) → Open connection → ws://100.100.254.86:8765 (Tailscale)
ros2 run nav2_map_server map_saver_cli -f ~/chicken_data/map   # 맵 저장
```

## 발행/구독
- 발행: /scan (laser_frame, 8.4 Hz), /map, /odometry/filtered, TF map→odom, odom→base_link(EKF 또는 fake), base_link→laser_frame(x 0.13, z 0.06, 임시 장착), base_link→imu_link(항등 — base_link 원점 = 보드 IMU)
- 구독: /odom, /imu/data_raw (odom:=ekf 일 때)

## 알아낸 것
- **라이다 속도는 DTR 선에 따라 바뀐다 (2026-10-28 측정)**: 포트를 연 프로그램이 DTR=on 이면 약 8.6 Hz, DTR=off 이거나 **포트를 아무도 안 열면 약 16 Hz 로 빨라진다**(진동 커짐). 드라이버(support_motor_dtr: true)가 떠 있을 때만 느리다. 8.6 Hz 보다 더 낮추려면 M_SCTP 하드웨어 제어가 필요.
- 라이다 임시 장착(2026-10-08): 회전 중심이 IMU(=base_link) 기준 앞 13 cm·위 6 cm, 정면 정렬. 실측 회전 8.4~8.7 Hz — X2 데이터시트 권장 7 Hz 보다 빠르다.
- 라이다가 도는 중에도 자이로 gz σ=0.00047 rad/s (정지 기준값 0.0004 와 같음) → 진동이 EKF 회전 입력을 망치지는 않음. 가속도 z σ 는 0.016→0.033 으로 늘었지만 EKF 에 안 씀.
- 원격 보기는 foxglove_bridge(apt ros-jazzy-foxglove-bridge 3.6.0, 2026-10-08 설치). mapping.launch.py 가 기본으로 8765 포트에 띄움(foxglove:=false 로 끔).
- 기종: 판매 페이지는 X4 Pro/X3/X2L 선택형. 115200·단방향이라 X2L 또는 X3 — 드라이버 params 의 X2.yaml 과 X3.yaml 은 내용이 같다.
- third_party/ 의 YDLidar-SDK(42a82ed), ydlidar_ros2_driver(humble 브랜치, 4ef70d3) 는 외부 코드라 수정하지 않는다. 설정은 chicken_slam/config/lidar.yaml.
- SDK 는 정적 라이브러리(libydlidar_sdk.a)만 설치되고, 드라이버가 그 경로를 몰라 링크 실패 → 위 LINKER_FLAGS 로 해결. sudo make install 불필요.
- 드라이버 시작 직후 Checksum error 몇 건과 Fail to get baseplate device information 은 정상(단방향 기종, 동기화 중).
- Real points 473 > fixed points 470 경고가 계속 나온다: 실제 회전 8.4 Hz 라 한 바퀴 점이 고정 해상도보다 3~4개 많아 버려지는 것. 맵에는 영향 미미.
- slam_toolbox minimum_travel_distance/heading = 0.1 (기본 0.5 보다 촘촘). 제자리 fake odom 에서 손으로 돌리며 그리려면 0 으로 낮춰야 한다.
- EKF 는 상태량마다 입력 하나: vx·vy 는 바퀴, vyaw 는 IMU 자이로. 바퀴 wz 가 명령보다 작게 나오는 현상(base/README) 때문에 회전은 자이로만 믿는다.
- 드라이버 시작 후 5~10초는 Checksum error / intensity adjusted 로그가 많다(SDK 가 세기 비트 형식을 자동 탐지). 그 뒤 안정.
- 라이다 포트는 `/dev/lidar` 로 고정(udev `/etc/udev/rules.d/99-chicken-serial.rules`).
- 라이다: CP2102(10c4:ea60, by-id usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0) → /dev/ttyUSB0, 115200 bps.
  YDLIDAR 프로토콜(AA 55 헤더, 명령 없이 자동 출력) — X2 계열로 보임. 8.4 Hz 회전, 약 4000 샘플/s(회전당 약 470점), 거리 = 값/4 mm. 5초 591패킷 체크섬 오류 0.

## 다음 할 일
- 라이다 회전 속도 낮추기(진동): M_SCTP 핀 전압/PWM 으로만 가능, 소프트웨어 설정 불가. 바꾼 뒤 lidar.yaml frequency 와 Real points 경고 확인
- 오도메트리 검증: 1 m 직진 → /odometry/filtered x≈1.0, 제자리 360° → yaw 한 바퀴 (바퀴 스케일·자이로 단위 확인)
- 천천히 주행하며 이동 맵핑, 루프 클로징 확인, 맵 저장

## 요청

## 작업 기록
- 2026-10-08 · Claude · 라이다 TF(앞 13 cm, 위 6 cm) 반영, 라이다 진동의 IMU 영향 측정
- 2026-10-08 · Claude · EKF(ekf.yaml) 추가, mapping.launch.py odom:=ekf|fake, travel 임계 0.1
- 2026-10-08 · Claude · YDLidar SDK/드라이버 빌드, chicken_slam 패키지(mapping.launch.py) 작성, 제자리 맵 생성 확인
- 2026-10-08 · Claude · 라이다 포트·프로토콜 확인
