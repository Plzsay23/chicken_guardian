# 방역 기록 대시보드

순찰 기록(JSON·사진)과 SLAM 지도를 읽어 침입 지점 지도와 구역별 이력을 보여주는 HTML 한 장을 만든다.

| 파일 | 하는 일 |
|---|---|
| `make_sample.py` | 예시 데이터 생성: 계사 외곽 지도(`map.pgm/yaml`), 구역(`zones.json`), 6회 순찰 기록(`records/`) |
| `dashboard.py` | 지도 + 기록 → `out/dashboard.html`(인터넷 없이 열림), `out/map_overlay.png`(보고서용 정적 이미지) |

```
py make_sample.py
py dashboard.py --map sample/map.yaml --records sample/records --zones sample/zones.json --out out
```

실제 로봇에서는 `--map` 에 slam_toolbox `map_saver` 결과, `--records` 에 `~/chicken/records` 를 넣는다.
기록 형식은 `docs/설계/02_소프트웨어_설계서.md` 4절(patrol_id, time, pose{x,y}, camera, class, count, max_conf, image, zone, night).
구역은 벽을 따라 6 m 단위 선분(`{zone, a:[x,y], b:[x,y]}`)이고, 흔적 수는 사료(feed_pellet)를 빼고 센다.
예시 사진은 `references/images` 의 공개 사진(Matt Frye/NYSIPM, CC BY 2.0)을 잘라 쓴 것이다.
