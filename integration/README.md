# integration — 통합

## 상태
- 시작 전

## 실행 방법

## 발행/구독

## 알아낸 것
- **센서 장착 위치 실측값 (2026-10-08, base 파트 + 사람)** — URDF 만들 때 사용:
  - `base_link` 원점 = 제어보드(IMU) 위치로 정의됨 (slam 파트 관례). `imu_link`는 `base_link`와 동일(오프셋 0).
  - `laser_frame`(라이다 회전축): `base_link` 기준 **앞으로 13cm, 위로 6cm, 좌우 0(정면 정렬)**. 줄자 실측 확인됨.
  - 지금은 `chicken_slam/launch/mapping.launch.py`에 `static_transform_publisher`로 임시 하드코딩되어 있음 — URDF 패키지가 여기 생기면 그쪽으로 옮길 것.
  - M500 고무바퀴 버전 제조사 치수(참고용, 섀시 visual/collision 박스 그릴 때): 폭 300mm, 축간거리(휠베이스) 340.4mm, 바퀴 지름 130mm, 전장 약 520mm. 제조사 자료 기준 오차 1~10mm 있을 수 있음.

## 다음 할 일
- 위 실측값으로 URDF(xacro) 작성, `robot_state_publisher`로 교체 (지금은 `chicken_slam`이 임시로 `static_transform_publisher` 여러 개 띄워서 때움)

## 요청

## 작업 기록
- 2026-10-08 · Claude + 사람 · 라이다/IMU 장착 위치 실측 확인 (알아낸 것 참고). URDF 작성 전 단계.
