# deterrence — 퇴치

## 상태
- 2026-10-28 USB DAC(MAXTEK MT979, CX31993+MAX97220) 인식 — aplay 카드 이름 `CX31993MAX97220`. 허브 1번 포트에선 -71 오류로 인식 실패, 다른 포트에선 정상.
- 가청 시험음 스크립트 tools/tone.py — **2026-10-28 피에조로 아주 잘 들림 확인(기본 vol 0.3 도 귀가 아플 만큼 큼)**. 22 kHz 는 아직.

## 실행 방법
```bash
python3 ~/chicken/deterrence/tools/tone.py            # 500/1000/2000/4000 Hz 각 1초
```

## 발행/구독

## 알아낸 것
- ALSA 별칭 **`dac`** (/etc/asound.conf, 2026-10-28): 카드 이름 CX31993MAX97220 으로 찾으므로 허브 포트·카드 번호가 바뀌어도 `aplay -D dac` 로 재생된다. 원본 백업 /etc/asound.conf.bak-chicken.
- 배선: 허브 → Coms BE732(C암→A수) → MT979 → 3.5mm → MAXTEK MT350(터미널) L·GND → 태진 MOP386-01(LM386) IN·GND, 앰프 VCC/GND ← XL4015 5.1V, 앰프 OUT/GND 나사단자 → 피에조 트위터 38×40mm.
- 앰프 입력은 L 채널만 쓴다(모노). DAC 지원 레이트 최대 384 kHz — 22 kHz 재생에 충분.

## 다음 할 일
- 가청음 확인 → 22 kHz 재생 확인 → ROS 노드

## 요청

## 작업 기록
- 2026-10-28 · Claude · 파트 폴더 생성, DAC 인식 확인, tools/tone.py
