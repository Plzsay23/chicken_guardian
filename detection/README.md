# 소형 흔적 탐지 (쥐 배설물·흘린 사료)
계사 외곽 순찰 로봇용 FR-05(쥐 배설물 탐지) 전용 모델. 5-40 px 크기 정지 객체를 원본 해상도 타일로 잘라 P2 head YOLO11로 탐지함.
## 설계 요약
- 대상 클래스: 0 rodent_dropping, 1 feed_pellet. 흘린 사료는 배설물과 가장 헷갈리는 대상이라 별도 클래스로 학습시켜 오탐을 흡수함(FR-08 겸용).
- 크기 문제: 실사진(references/images) 기준 배설물 중앙값 12x9 px / 1920x1440. 프레임 전체를 640으로 줄이면 3-4 px → 소실. 그래서 축소 없이 640 타일(겹침 20%)로 자름.
- 모델: models/yolo11-p2.yaml. YOLO11에 stride 4 P2 head 추가. 0-16층은 yolo11 그대로라 COCO 가중치 이식 가능. yolo11s-p2 = 9.56M params, 28.7 GFLOPs.
- 추론 2단(FR-04): patrol = 주행 중 겹침 10%·낮은 conf로 재현율 우선 → /traces/candidate. confirm = 정지 후 겹침 25% + 상하좌우 flip TTA로 정밀도 우선 → 사진·JSON·위치 기록(FR-10).
- 타일 경계 중복은 IoU가 아닌 IoS(작은 박스 기준 겹침) NMS로 병합. 잘린 조각 박스가 IoU로는 안 지워지기 때문.
- 데이터: 공개 쥐 배설물 bbox 데이터셋 사실상 없음(2026-10-19 조사). 절차형 합성 데이터로 부트스트랩 → 현장 실사진으로 fine-tune. 합성에는 자갈·왕겨·잔가지·흙덩이·씨앗·깃털 등 비슷한 비라벨 물체를 대량으로 넣어 hard negative로 씀. 야간 NoIR+940nm 모사 30%(FR-12), 주행 motion blur 30%.
- 평가: 타일 mAP는 학습 신호일 뿐. scripts/evaluate.py가 전체 프레임 sliced 결과로 AP@IoU0.3, 크기 구간별 recall, FPPI, 프레임 단위 "배설물 있음" 판정을 냄. 작은 박스는 2 px 어긋나도 IoU 0.5가 깨져 0.3을 기본으로 둠.
- 현재 유일한 실사진 라벨(references 48박스, CC BY 2.0)은 학습에 쓰지 않고 sim-to-real 확인용으로만 씀.
## 폴더
- configs/traces.yaml: 클래스·타일·추론 모드·합성 설정. 모든 스크립트 공통
- traces/: 공용 라이브러리(tiling, synth, sliced 추론, metrics, imgio)
- scripts/: 단계별 실행 스크립트
- ros2/chicken_detection/: 젯슨용 ROS 2 패키지(Jazzy, ament_python)
- data/, runs/, weights/: 생성물. 용량 크고 재생성 가능
## 환경
M:는 네트워크 공유(\\100.89.50.50\main)라 venv·학습 데이터를 올리면 느림. PC 로컬 venv는 C:\ysj\.venvs\traces (torch 2.11+cu128, ultralytics 8.4). 데이터·runs도 로컬 디스크 경로를 --out/--project로 주는 것을 권장.
```bash
python -m venv C:/ysj/.venvs/traces
C:/ysj/.venvs/traces/Scripts/python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
C:/ysj/.venvs/traces/Scripts/python -m pip install ultralytics onnx onnxslim pyyaml
```
한글 경로 때문에 export PYTHONUTF8=1 을 켜고 실행. 아래 명령은 detection/ 에서 실행하며 PY=C:/ysj/.venvs/traces/Scripts/python, W=로컬 작업 폴더(예: C:/ysj/traces_work).
## 0. 학습 장비 - 토르
학습은 토르(Jetson AGX Thor, ssh hansungai@100.116.55.6)에서 함. venv ~/venv/traces(torch cu130), 코드 ~/traces/code, 데이터·결과 ~/traces/{raw,tiles,runs,logs}. 실행은 tmux 세션 traces 안에서 ~/traces/run_synth_v2.sh 처럼 단계 스크립트로. 코드 동기화는 PC detection/ 에서 scp -r traces scripts configs models hansungai@100.116.55.6:traces/code/
## 1. 합성 데이터 생성
```bash
$PY scripts/make_synth.py \
  --cfg configs/traces.yaml \
  --out $W/raw/synth \
  --n 3000 \
  --seed 0 \
  --bg-dir $W/backgrounds \
  --sprite-dir $W/sprites \
  --preview 6
```
| 인자 | 기본 | 뜻 |
|---|---|---|
| --cfg | configs/traces.yaml | 공통 설정. 클래스 순서가 곧 class id |
| --out | data/raw/synth | 원본 해상도 프레임 + YOLO 라벨 출력 폴더 |
| --n | 600 | 프레임 수. 1920x1080 한 장 약 0.5 s, 타일 약 6장 |
| --seed | 0 | 시드. 추가 생성 시 바꿔야 파일명이 안 겹침 |
| --bg-dir | data/backgrounds | 배설물 없는 현장 바닥 사진. 있으면 70% 확률로 배경에 씀. 현장 사진 확보 시 가장 효과 큰 입력 |
| --sprite-dir | data/sprites | <클래스명>/*.png RGBA 오려낸 실물. 있으면 50% 확률로 절차형 대신 씀 |
| --preview | 6 | 박스 그린 확인용 프레임 수(preview/ 폴더) |
## 2. 실사진 기준셋 가져오기
```bash
$PY scripts/import_reference.py \
  --out $W/raw/reference
```
| 인자 | 기본 | 뜻 |
|---|---|---|
| --image | references/images/house_mouse_droppings_NYSIPM_CCBY2.jpg | 유일한 실사진 라벨 |
| --boxes | references/images/라벨링예시_배설물_boxes.json | [x, y, w, h, 어두움] 48행 |
| --out | data/raw/reference | YOLO 형식 출력 |
--sprites 를 주면 48개를 RGBA로 오려 data/sprites/rodent_dropping/ 에 저장함. 이 경우 이 사진으로 평가하면 누수이므로 평가에서 뺄 것.
## 2-1. 실물 스프라이트 오려내기
```bash
$PY scripts/extract_sprites.py \
  --images data/external/wikimedia/wiki_00.jpg data/external/wikimedia/wiki_07.jpg \
  --out data/sprites/rodent_dropping \
  --prefix wiki \
  --dark-margin 60 \
  --alpha-offset 15
```
| 인자 | 기본 | 뜻 |
|---|---|---|
| --images | (필수) | 흰 종이·단색 바닥 위에서 찍은 배설물 사진. 복잡한 바닥 사진은 안 됨 |
| --out | (필수) | 1단계 --sprite-dir 아래 <클래스명> 폴더 |
| --prefix | ext | 파일명 앞머리 |
| --dark-margin | 60 | 배경보다 이만큼 어두워야 물체로 봄 |
| --alpha-offset | 15 | 유색 배경이면 올려서(예 70) 배경색 테두리를 지움 |
<out>/_sheet_<prefix>.jpg 를 보고 붙은 덩어리·눈금자 숫자 등 불량 스프라이트는 손으로 지움. 현재 data/sprites/rodent_dropping 15개(위키미디어 쥐·생쥐, 출처는 data/external/wikimedia/manifest.json).
## 3. 타일 데이터셋 만들기
```bash
$PY scripts/prepare_dataset.py \
  --cfg configs/traces.yaml \
  --raw $W/raw/synth \
  --val-raw $W/raw/reference \
  --val-frac 0.15 \
  --out $W/tiles/synth_v1 \
  --seed 0
```
| 인자 | 기본 | 뜻 |
|---|---|---|
| --raw | (필수) | 원본 데이터 폴더 여러 개. images/[세션폴더/]*.jpg + labels/ |
| --val-raw | 없음 | 통째로 검증에만 쓸 폴더 |
| --val-frac | 0.15 | 그룹 단위 검증 비율. 그룹 = images/ 밑 첫 하위폴더(촬영 세션), 없으면 사진 1장 |
| --out | data/tiles/default | 타일 출력. data.yaml, val_full.txt 생성 |
| --seed | 0 | 분할·빈 타일 샘플링 시드 |
기존 출력 폴더를 다시 만들 때만 --overwrite. 라벨 파일이 없는 이미지는 음성(배경) 사진으로 취급함.
## 4. 학습 (1단계: 합성 부트스트랩)
```bash
$PY scripts/train.py \
  --cfg configs/traces.yaml \
  --data $W/tiles/synth_v1/data.yaml \
  --model models/yolo11s-p2.yaml \
  --pretrained yolo11s.pt \
  --epochs 80 \
  --batch 16 \
  --workers 4 \
  --optimizer auto \
  --lr0 0.01 \
  --patience 25 \
  --cache False \
  --project $W/runs \
  --name synth_v1 \
  --seed 0
```
| 인자 | 기본 | 뜻 |
|---|---|---|
| --data | (필수) | 3단계 data.yaml |
| --model | models/yolo11s-p2.yaml | 파일명 속 n/s/m 이 scale. 실제 파일은 yolo11-p2.yaml 하나. .pt를 주면 fine-tune |
| --pretrained | yolo11s.pt | yaml 모델에 이식할 COCO 가중치. scale 글자와 맞출 것. none이면 생략 |
| --epochs | 80 | 에폭 |
| --batch | 16 | RTX 4060 8GB에서 s-p2 640 batch 8이 3.3 GB. 16까지 무난 |
| --workers | 4 | dataloader 프로세스 |
| --optimizer | auto | auto는 --lr0를 무시함. SGD/AdamW를 줘야 lr0가 먹음 |
| --lr0 | 0.01 | 초기 학습률 |
| --patience | 25 | early stop |
| --cache | False | ram이면 빠르나 타일 수만큼 메모리 사용 |
| --project / --name | runs / traces | 결과 폴더. weights/best.pt |
| --device | 자동 | 0, cpu, 0,1 |
증강은 train.py 안에 고정: scale 0.25(기본 0.5면 8 px가 4 px로 줄어 P2로도 못 잡음), degrees 0, flipud 0.5(지면을 위에서 봄), mosaic 1.0.
## 5. 학습 (2단계: 실사진 fine-tune)
```bash
$PY scripts/prepare_dataset.py \
  --raw $W/raw/farm_2026_10 $W/raw/synth \
  --val-frac 0.2 \
  --out $W/tiles/farm_v1
$PY scripts/train.py \
  --data $W/tiles/farm_v1/data.yaml \
  --model $W/runs/synth_v1/weights/best.pt \
  --pretrained none \
  --epochs 60 \
  --batch 16 \
  --optimizer AdamW \
  --lr0 0.0005 \
  --project $W/runs \
  --name farm_v1
```
현장 사진은 images/<촬영세션>/ 아래에 두고 라벨링 도구(X-AnyLabeling, CVAT 등)에서 YOLO 형식으로 내보냄. 박스는 배설물 한 알씩 꼭 맞게. 사료가 뭉친 덩어리는 알갱이 구분이 안 되면 덩어리 하나로. 합성은 실사진 대비 1:1 이하로 섞음.
## 6. 평가 (전체 프레임)
```bash
$PY scripts/evaluate.py \
  --cfg configs/traces.yaml \
  --weights $W/runs/synth_v1/weights/best.pt \
  --images $W/raw/reference/images \
  --mode confirm \
  --iou 0.3 \
  --max-vis 20 \
  --out $W/runs/synth_v1/eval_reference
```
| 인자 | 기본 | 뜻 |
|---|---|---|
| --images | (필수) | 원본 해상도 폴더 또는 3단계 val_full.txt |
| --mode | confirm | configs 의 infer.patrol / infer.confirm 설정 사용 |
| --iou | 0.3 | 매칭 IoU. 작은 박스라 느슨하게 |
| --conf | 모드 conf | P/R/F1/FPPI 계산용 운용 임계값 |
| --max-vis | 20 | 결과 그림 수. 초록 TP, 빨강 FP, 파랑 놓친 GT |
| --out | weights 옆 eval_<mode>_<폴더> | metrics.json + vis/ |
--tune-conf 를 주면 클래스 0 F1 최대 conf도 출력. 검증셋에서 정하고 configs 에 반영. 평가용 라벨에서 class -1 행은 무시 영역(뭉친 배설물 등)으로, 그 안의 예측은 TP도 FP도 아님. 학습 데이터에는 -1 금지.
현재 라벨된 실사진 평가셋: data/raw/reference(48박스) + data/raw/wiki_eval(wiki_06, 7박스, 1/4 축소). 정성 확인용 사진은 data/qual.
## 7. 추론 (사진·폴더·영상)
```bash
$PY scripts/infer.py \
  --weights $W/runs/synth_v1/weights/best.pt \
  --source some/folder_or_video.mp4 \
  --mode confirm \
  --vid-stride 5 \
  --out $W/runs/infer
```
| 인자 | 기본 | 뜻 |
|---|---|---|
| --source | (필수) | 이미지, 폴더, 영상 |
| --mode | confirm | patrol 은 빠르고 conf 낮음 |
| --conf | 모드 conf | 임계값 덮어쓰기 |
| --vid-stride | 5 | 영상은 n 프레임마다 처리 |
| --out | runs/infer | 그림 + detections.json |
## 8. 내보내기
```bash
$PY scripts/export.py \
  --weights $W/runs/synth_v1/weights/best.pt \
  --format onnx \
  --batch 1
```
| 인자 | 기본 | 뜻 |
|---|---|---|
| --format | onnx | onnx(PC 확인용) / engine(TensorRT, 반드시 젯슨에서 빌드) |
| --batch | 1 | 고정 batch. sliced 추론이 .onnx/.engine 은 타일을 1장씩 보냄 |
| --data | 없음 | INT8 보정용 data.yaml(--int8 과 함께) |
젯슨 FP16: python3 scripts/export.py --weights best.pt --format engine --half. INT8은 --int8 --data <data.yaml>. TensorRT 엔진은 GPU·TensorRT 버전에 묶이므로 PC에서 만든 engine을 옮기지 말 것.
## 9. 로봇 (ROS 2 Jazzy, 젯슨 ~/chicken)
detection/ 을 젯슨 ~/chicken/detection 으로 복사(traces/ configs/ 포함). 젯슨 python 에 ultralytics 필요.
```bash
cd ~/chicken && colcon build --packages-select chicken_detection --base-paths detection/ros2
source install/setup.bash
ros2 run chicken_detection trace_node --ros-args \
  -p traces_root:=$HOME/chicken/detection \
  -p weights:=$HOME/chicken/detection/weights/best.engine \
  -p image_topic:=/camera/front/image_raw \
  -p patrol_hz:=2.0 \
  -p record_dir:=$HOME/chicken/records/traces \
  -p map_frame:=map \
  -p base_frame:=base_link \
  -p alarm_class:=0 \
  -p max_frame_age_s:=1.0
```
| 인자 | 기본 | 뜻 |
|---|---|---|
| traces_root | ~/chicken/detection | traces 패키지·configs 위치 |
| weights | <traces_root>/weights/best.engine | .engine/.onnx/.pt 모두 가능 |
| image_topic | /camera/front/image_raw | 카메라 토픽. 카메라 드라이버 확정 후 맞출 것 |
| patrol_hz | 2.0 | 주행 중 1차 탐지 주기 |
| record_dir | ~/chicken/records/traces | 확인 결과 원본·그림·JSON 저장. 원본은 다음 학습 데이터 |
| map_frame / base_frame | map / base_link | 기록할 로봇 위치 TF |
| alarm_class | 0 | 정지 후보를 띄울 클래스 |
| max_frame_age_s | 1.0 | 이보다 오래된 프레임은 무시 |
INTERFACES.md 에 추가할 항목: 구독 image_topic(sensor_msgs/Image). 발행 /traces/detections, /traces/confirmed(vision_msgs/Detection2DArray), /traces/candidate(std_msgs/Bool, true면 내비게이션이 정지). 서비스 /traces/confirm(std_srvs/Trigger, 정지 후 호출, message에 클래스별 개수 JSON).
## 주의
- 합성만으로 학습한 모델은 실사진 성능이 보장되지 않음. 현장 바닥 사진(배경)과 실물 배설물·사료 사진 확보가 1순위.
- configs 의 classes 순서를 바꾸면 기존 라벨·가중치와 호환이 깨짐.
- 평가 지표는 반드시 evaluate.py(전체 프레임) 기준으로 보고. 학습 로그의 타일 mAP와 다름.
- ROS 2 노드는 Windows에서 문법 검사만 함. 젯슨 실행 검증 전.
