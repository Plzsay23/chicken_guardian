"""예시 데이터 생성: 계사 외곽 SLAM 지도(map.pgm/yaml) + 순찰 기록(JSON·사진)

실제 로봇에서는 slam_toolbox 가 저장한 지도와 ~/chicken/records/ 가 이 자리에 온다.
사용: py make_sample.py [출력폴더]   (기본 ./sample)
"""
import json, math, random, sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "sample")
RES = 0.05                     # m/px (slam_toolbox 기본)
W_M, H_M = 64.0, 28.0          # 지도 크기 (m)
ORIGIN = (-8.0, -8.0)          # 지도 왼쪽 아래 픽셀의 월드 좌표
BLD = (0.0, 0.0, 48.0, 12.0)   # 계사 외벽 (x0, y0, x1, y1), m
WALL_GAP = 0.6                 # 벽 추종 거리
SEG = 6.0                      # 구역 길이 (m)

random.seed(7)
np.random.seed(7)


def w2p(x, y):
    """월드(m) → 이미지 픽셀(위가 +y)"""
    px = (x - ORIGIN[0]) / RES
    py = (H_M - (y - ORIGIN[1])) / RES
    return px, py


def make_map():
    w, h = int(W_M / RES), int(H_M / RES)
    img = Image.new("L", (w, h), 205)              # 205 = 미확인(회색)
    d = ImageDraw.Draw(img)
    # 로봇이 본 자유 공간: 외벽 둘레 띠 + 약간의 불규칙
    x0, y0, x1, y1 = BLD
    for k in range(5):
        m = 4.0 + random.uniform(-0.6, 0.8)
        a = w2p(x0 - m, y1 + m); b = w2p(x1 + m, y0 - m)
        d.rectangle([a, b], fill=254)
    # 계사 내부는 못 봄
    a = w2p(x0, y1); b = w2p(x1, y0)
    d.rectangle([a, b], fill=205)
    # 외벽(점유)
    d.rectangle([a, b], outline=0, width=4)
    # 출입문·환기구 등 벽 요철
    for x in (8, 20, 32, 44):
        p, q = w2p(x, y0 - 0.0), w2p(x + 1.5, y0 - 0.5)
        d.rectangle([p, q], fill=0)
    # 주변 장애물(적치물·수풀·사료빈)
    for cx, cy, r in [(-4, 3, 0.8), (52, 9, 1.1), (15, 16.5, 0.6), (38, -4.5, 0.9), (26, 17, 0.5)]:
        p, q = w2p(cx - r, cy + r), w2p(cx + r, cy - r)
        d.ellipse([p, q], fill=0)
    # 라이다 잡음
    arr = np.array(img)
    free = arr == 254
    noise = (np.random.rand(*arr.shape) < 0.0015) & free
    arr[noise] = 0
    img = Image.fromarray(arr)
    OUT.mkdir(parents=True, exist_ok=True)
    img.save(OUT / "map.pgm")
    (OUT / "map.yaml").write_text(
        "image: map.pgm\nmode: trinary\nresolution: %.3f\norigin: [%.1f, %.1f, 0.0]\n"
        "negate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n" % (RES, ORIGIN[0], ORIGIN[1]),
        encoding="utf-8")


def patrol_path():
    """외벽에서 0.6 m 떨어진 폐곡선 + 구역 이름"""
    x0, y0, x1, y1 = BLD
    g = WALL_GAP
    sides = [("A", (x0 - g, y0 - g), (x1 + g, y0 - g)),   # 남쪽
             ("B", (x1 + g, y0 - g), (x1 + g, y1 + g)),   # 동쪽
             ("C", (x1 + g, y1 + g), (x0 - g, y1 + g)),   # 북쪽
             ("D", (x0 - g, y1 + g), (x0 - g, y0 - g))]   # 서쪽
    return sides


def zones():
    out = []
    for name, a, b in patrol_path():
        L = math.dist(a, b); n = max(1, round(L / SEG))
        for i in range(n):
            t0, t1 = i / n, (i + 1) / n
            out.append({"zone": "%s-%d" % (name, i + 1),
                        "a": [a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0],
                        "b": [a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1]})
    return out


def thumbs():
    """예시 사진: references 의 공개 배설물 사진(CC BY 2.0)에서 잘라 쓴다. 없으면 회색 판."""
    src = Path(__file__).resolve().parents[2] / "references" / "images" / "house_mouse_droppings_NYSIPM_CCBY2.jpg"
    crops = []
    if src.exists():
        im = Image.open(src).convert("RGB")
        for cx, cy in [(960, 790), (1180, 870), (600, 900), (1290, 1180), (1050, 1000), (1520, 760)]:
            crops.append(im.crop((cx - 160, cy - 120, cx + 160, cy + 120)))
    else:
        crops = [Image.new("RGB", (320, 240), (150, 140, 120))]
    return crops


def make_records():
    zs = zones()
    hot = {"A-3": 5, "A-6": 3, "B-1": 2, "C-2": 4, "C-5": 1, "D-2": 2}   # 흔적이 잘 나오는 구역
    crops = thumbs()
    start = datetime(2026, 11, 16, 21, 0)
    rec_root = OUT / "records"
    k = 0
    for day in range(6):
        night = day % 2 == 0
        t = start + timedelta(days=day, hours=0 if night else -10)
        pid = t.strftime("%Y-%m-%d_%H-%M")
        pdir = rec_root / t.strftime("%Y-%m-%d") / pid
        pdir.mkdir(parents=True, exist_ok=True)
        dets = []
        for z in zs:
            lam = hot.get(z["zone"], 0.15) * (0.6 + 0.15 * day)        # 날이 갈수록 조금 늘어남
            for _ in range(np.random.poisson(lam * 0.45)):
                u = random.random()
                x = z["a"][0] + (z["b"][0] - z["a"][0]) * u
                y = z["a"][1] + (z["b"][1] - z["a"][1]) * u
                cls = random.choices(["rodent_dropping", "feed_pellet", "wall_hole"], [0.62, 0.28, 0.10])[0]
                cam = random.choice(["left", "right", "front"])
                k += 1
                img_name = "%06d_%s.jpg" % (k, cam)
                crops[k % len(crops)].save(pdir / img_name, quality=80)
                dets.append({
                    "patrol_id": pid,
                    "time": (t + timedelta(minutes=random.uniform(2, 40))).strftime("%Y-%m-%dT%H:%M:%S+09:00"),
                    "pose": {"frame": "map", "x": round(x + random.gauss(0, 0.08), 2),
                             "y": round(y + random.gauss(0, 0.08), 2), "yaw": 0.0},
                    "camera": cam, "class": cls,
                    "count": random.randint(1, 9) if cls == "rodent_dropping" else 1,
                    "max_conf": round(random.uniform(0.45, 0.93), 2),
                    "image": img_name, "zone": z["zone"], "night": night})
        for i, d in enumerate(sorted(dets, key=lambda d: d["time"])):
            (pdir / ("%06d.json" % i)).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "zones.json").write_text(json.dumps(zs, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    make_map()
    make_records()
    print("sample ->", OUT)
