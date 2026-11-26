"""방역 기록 대시보드: SLAM 지도 + 순찰 기록(JSON) → dashboard.html, map_overlay.png

입력
  지도   : slam_toolbox map_saver 결과 (map.yaml + map.pgm)
  기록   : records/<날짜>/<순찰ID>/*.json  (소프트웨어 설계서 4절 형식) + 같은 폴더의 사진
  구역   : zones.json  [{zone, a:[x,y], b:[x,y]}]  (없으면 기록의 zone 이름만 사용)
사용
  py dashboard.py --map sample/map.yaml --records sample/records --zones sample/zones.json --out out
"""
import argparse, base64, io, json
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CLASS_KO = {"rodent_dropping": "설치류 배설물", "feed_pellet": "흘린 사료", "wall_hole": "벽면 구멍"}
CLASS_RGB = {"rodent_dropping": (214, 69, 65), "feed_pellet": (232, 160, 32), "wall_hole": (59, 110, 214)}


def load_map(yaml_path):
    y = {}
    for line in Path(yaml_path).read_text(encoding="utf-8").splitlines():
        if ":" in line:
            k, v = line.split(":", 1); y[k.strip()] = v.strip()
    img = Image.open(Path(yaml_path).parent / y["image"]).convert("L")
    res = float(y["resolution"])
    ox, oy = [float(v) for v in y["origin"].strip("[]").split(",")[:2]]
    return img, res, ox, oy


def load_records(root):
    recs = []
    for f in sorted(Path(root).glob("*/*/*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        d["_img"] = str(f.parent / d["image"]) if d.get("image") else None
        recs.append(d)
    return recs


def thumb_uri(path, size=(240, 180)):
    if not path or not Path(path).exists():
        return ""
    im = Image.open(path).convert("RGB"); im.thumbnail(size)
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=72)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def map_uri(img):
    rgb = Image.new("RGB", img.size)
    px = img.load(); out = rgb.load()
    for y in range(img.size[1]):           # 점유 0 / 자유 254 / 미확인 205 → 화면 색
        for x in range(img.size[0]):
            v = px[x, y]
            out[x, y] = (38, 42, 48) if v < 100 else ((246, 246, 243) if v > 250 else (214, 214, 208))
    buf = io.BytesIO(); rgb.save(buf, "PNG")
    return rgb, "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def overlay_png(base_rgb, recs, zones, res, ox, oy, path):
    """보고서·인쇄용 정적 이미지"""
    H = base_rgb.size[1]
    to_px = lambda x, y: ((x - ox) / res, H - (y - oy) / res)
    im = base_rgb.copy(); d = ImageDraw.Draw(im, "RGBA")
    zc = Counter(r["zone"] for r in recs if r["class"] != "feed_pellet")
    mx = max(zc.values() or [1])
    for z in zones:
        n = zc.get(z["zone"], 0)
        a, b = to_px(*z["a"]), to_px(*z["b"])
        d.line([a, b], fill=(214, 69, 65, int(40 + 200 * n / mx)) if n else (120, 160, 120, 120), width=14)
    for r in recs:
        x, y = to_px(r["pose"]["x"], r["pose"]["y"]); c = CLASS_RGB.get(r["class"], (90, 90, 90))
        d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=c + (230,), outline=(255, 255, 255, 255), width=2)
    try:
        f = ImageFont.truetype("malgun.ttf", 18)
    except OSError:
        f = ImageFont.load_default()
    for z in zones:
        (ax, ay), (bx, by) = to_px(*z["a"]), to_px(*z["b"])
        d.text(((ax + bx) / 2 + 6, (ay + by) / 2 + 6), z["zone"], fill=(60, 60, 60, 255), font=f)
    im.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True); ap.add_argument("--records", required=True)
    ap.add_argument("--zones"); ap.add_argument("--out", default="out")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    img, res, ox, oy = load_map(a.map)
    recs = load_records(a.records)
    zones = json.loads(Path(a.zones).read_text(encoding="utf-8")) if a.zones else []
    base_rgb, base_uri = map_uri(img)
    overlay_png(base_rgb, recs, zones, res, ox, oy, out / "map_overlay.png")

    data = {
        "map": {"uri": base_uri, "w": img.size[0], "h": img.size[1], "res": res, "ox": ox, "oy": oy},
        "zones": zones,
        "classes": {k: {"ko": CLASS_KO[k], "rgb": "rgb(%d,%d,%d)" % CLASS_RGB[k]} for k in CLASS_KO},
        "recs": [{k: v for k, v in r.items() if not k.startswith("_")} | {"thumb": thumb_uri(r["_img"])} for r in recs],
    }
    html = TEMPLATE.replace("/*DATA*/null", json.dumps(data, ensure_ascii=False))
    (out / "dashboard.html").write_text(html, encoding="utf-8")
    print("records %d, zones %d -> %s" % (len(recs), len(zones), out.resolve()))


TEMPLATE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>계사 방역 기록</title>
<style>
:root{--bg:#f4f3ef;--card:#fff;--ink:#22252a;--sub:#6b7078;--line:#e3e1db;--accent:#2f5d50;--hot:#d64541}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#16181b;--card:#1f2226;--ink:#e8e6e1;--sub:#9aa0a8;--line:#30343a;--accent:#7fb8a4}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 "Pretendard","Malgun Gothic",system-ui,sans-serif}
header{padding:20px 24px 8px;display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end;justify-content:space-between}
h1{margin:0;font-size:22px}header p{margin:2px 0 0;color:var(--sub)}
.ctl{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
select,label.chip{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px 10px;color:var(--ink);font:inherit}
label.chip{display:inline-flex;gap:6px;align-items:center;cursor:pointer}label.chip i{width:10px;height:10px;border-radius:50%;display:inline-block}
main{padding:8px 24px 32px;display:grid;gap:16px;grid-template-columns:minmax(0,2.2fr) minmax(280px,1fr)}
@media (max-width:900px){main{grid-template-columns:1fr;padding:8px 16px 24px}header{padding:16px}}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.kpis{grid-column:1/-1;display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.kpi b{display:block;font-size:26px;font-variant-numeric:tabular-nums}.kpi span{color:var(--sub);font-size:12px}
h2{font-size:15px;margin:0 0 10px}
#mapwrap{position:relative;width:100%;overflow:hidden;border-radius:8px;border:1px solid var(--line)}
#mapwrap img,#mapwrap svg{display:block;width:100%;height:auto}#mapwrap svg{position:absolute;inset:0}
.mk{cursor:pointer;stroke:#fff;stroke-width:2}.mk:hover,.mk.sel{stroke:#111;stroke-width:3}
.zl{font-size:22px;font-weight:600;fill:#4a4f57;paint-order:stroke;stroke:#f6f6f3;stroke-width:4px}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th,td{padding:6px 4px;border-bottom:1px solid var(--line);text-align:right}th:first-child,td:first-child{text-align:left}
th{color:var(--sub);font-weight:500;font-size:12px}
.bar{display:inline-block;height:8px;border-radius:4px;background:var(--hot);vertical-align:middle}
.spark{display:inline-flex;gap:2px;align-items:flex-end;height:18px}.spark i{width:5px;background:var(--accent);border-radius:1px}
#detail img{width:100%;border-radius:8px;margin:6px 0}#detail dl{display:grid;grid-template-columns:auto 1fr;gap:2px 10px;margin:0}#detail dt{color:var(--sub)}
.list{max-height:320px;overflow:auto}.row{display:flex;gap:10px;padding:6px 0;border-bottom:1px solid var(--line);cursor:pointer}
.row img{width:64px;height:48px;object-fit:cover;border-radius:4px}.row small{color:var(--sub)}
.note{color:var(--sub);font-size:12px;margin-top:8px}
</style></head><body>
<header><div><h1>계사 외곽 방역 기록</h1><p id="period"></p></div>
<div class="ctl"><select id="patrol"></select><span id="chips"></span></div></header>
<main>
 <section class="kpis" id="kpis"></section>
 <section class="card"><h2>침입 지점 지도</h2><div id="mapwrap"><img id="mapimg" alt="SLAM 지도"><svg id="ov"></svg></div>
  <p class="note">선 굵기·색 = 구역별 흔적 수(사료 제외) · 점 = 개별 탐지, 누르면 오른쪽에 사진</p></section>
 <section class="card" id="detail"><h2>탐지 상세</h2><p class="note">지도의 점이나 아래 목록을 누르세요</p></section>
 <section class="card"><h2>구역별 이력</h2><table id="zt"></table></section>
 <section class="card"><h2>최근 탐지</h2><div class="list" id="list"></div></section>
</main>
<script>
const D=/*DATA*/null;
const M=D.map, toPx=(x,y)=>[(x-M.ox)/M.res, M.h-(y-M.oy)/M.res];
const patrols=[...new Set(D.recs.map(r=>r.patrol_id))].sort();
const on=new Set(Object.keys(D.classes));
const $=id=>document.getElementById(id);
$('mapimg').src=M.uri; $('ov').setAttribute('viewBox',`0 0 ${M.w} ${M.h}`);
$('patrol').innerHTML='<option value="">전체 순찰 ('+patrols.length+'회)</option>'+patrols.map(p=>`<option>${p}</option>`).join('');
$('chips').innerHTML=Object.entries(D.classes).map(([k,c])=>`<label class="chip"><input type="checkbox" checked data-k="${k}"><i style="background:${c.rgb}"></i>${c.ko}</label>`).join('');
$('period').textContent=patrols.length?`${patrols[0].slice(0,10)} - ${patrols.at(-1).slice(0,10)} · 순찰 ${patrols.length}회`:'기록 없음';
document.querySelectorAll('#chips input').forEach(cb=>cb.onchange=()=>{cb.checked?on.add(cb.dataset.k):on.delete(cb.dataset.k);draw()});
$('patrol').onchange=draw;
function sel(){const p=$('patrol').value;return D.recs.filter(r=>(!p||r.patrol_id===p)&&on.has(r.class))}
function draw(){
 const R=sel(), traces=R.filter(r=>r.class!=='feed_pellet');
 const zc={};traces.forEach(r=>zc[r.zone]=(zc[r.zone]||0)+1);const mx=Math.max(1,...Object.values(zc));
 const drops=R.filter(r=>r.class==='rodent_dropping').reduce((s,r)=>s+(r.count||1),0);
 $('kpis').innerHTML=[[R.length,'탐지 기록'],[drops,'배설물 수량 합'],[Object.keys(zc).length+' / '+D.zones.length,'흔적 발견 구역'],
  [R.filter(r=>r.night).length,'야간 순찰 탐지']].map(([v,l])=>`<div class="card kpi"><b>${v}</b><span>${l}</span></div>`).join('');
 let s='';
 D.zones.forEach(z=>{const[a1,a2]=toPx(...z.a),[b1,b2]=toPx(...z.b),n=zc[z.zone]||0;
  s+=`<line x1="${a1}" y1="${a2}" x2="${b1}" y2="${b2}" stroke="${n?'#d64541':'#7fae86'}" stroke-opacity="${n?0.25+0.75*n/mx:0.45}" stroke-width="${n?8+14*n/mx:6}" stroke-linecap="round"/>`;
  s+=`<text class="zl" text-anchor="middle" x="${(a1+b1)/2+(a1===b1?(a1<M.w/2?-34:34):0)}" y="${(a2+b2)/2+(a2===b2?(a2<M.h/2?-16:30):6)}">${z.zone}</text>`});
 R.forEach((r,i)=>{const[x,y]=toPx(r.pose.x,r.pose.y);s+=`<circle class="mk" data-i="${D.recs.indexOf(r)}" cx="${x}" cy="${y}" r="10" fill="${D.classes[r.class].rgb}"/>`});
 $('ov').innerHTML=s; $('ov').querySelectorAll('.mk').forEach(c=>c.onclick=()=>show(+c.dataset.i));
 // 구역 표: 순찰별 막대(작은 스파크) + 합계
 const byZ={};D.recs.filter(r=>on.has(r.class)&&r.class!=='feed_pellet').forEach(r=>{(byZ[r.zone]??={})[r.patrol_id]=((byZ[r.zone]||{})[r.patrol_id]||0)+1});
 const rows=D.zones.map(z=>z.zone).filter(z=>zc[z]).sort((a,b)=>zc[b]-zc[a]);
 const pm=Math.max(1,...rows.flatMap(z=>Object.values(byZ[z]||{})));
 $('zt').innerHTML='<tr><th>구역</th><th>순찰별 추이</th><th>흔적</th><th></th></tr>'+rows.map(z=>`<tr><td>${z}</td><td><span class="spark">${patrols.map(p=>`<i style="height:${2+16*((byZ[z]||{})[p]||0)/pm}px" title="${p}: ${(byZ[z]||{})[p]||0}"></i>`).join('')}</span></td><td>${zc[z]}</td><td style="width:35%"><span class="bar" style="width:${100*zc[z]/mx}%"></span></td></tr>`).join('')||'<tr><td colspan="4">흔적 없음</td></tr>';
 $('list').innerHTML=[...R].sort((a,b)=>b.time.localeCompare(a.time)).slice(0,60).map(r=>`<div class="row" data-i="${D.recs.indexOf(r)}">${r.thumb?`<img src="${r.thumb}" alt="">`:''}<div>${D.classes[r.class].ko} · ${r.zone}<br><small>${r.time.replace('T',' ').slice(0,16)} · ${r.camera} · conf ${r.max_conf}</small></div></div>`).join('');
 $('list').querySelectorAll('.row').forEach(e=>e.onclick=()=>show(+e.dataset.i));
}
function show(i){const r=D.recs[i];
 document.querySelectorAll('.mk').forEach(c=>c.classList.toggle('sel',+c.dataset.i===i));
 $('detail').innerHTML=`<h2>탐지 상세</h2>${r.thumb?`<img src="${r.thumb}" alt="탐지 사진">`:''}<dl>
 <dt>분류</dt><dd>${D.classes[r.class].ko}${r.class==='rodent_dropping'?` ${r.count}개`:''}</dd><dt>구역</dt><dd>${r.zone}</dd>
 <dt>위치</dt><dd>x ${r.pose.x} m, y ${r.pose.y} m</dd><dt>시각</dt><dd>${r.time.replace('T',' ').slice(0,19)}${r.night?' (야간)':''}</dd>
 <dt>카메라</dt><dd>${r.camera}</dd><dt>신뢰도</dt><dd>${r.max_conf}</dd><dt>순찰</dt><dd>${r.patrol_id}</dd></dl>`}
draw();
const first=sel().sort((a,b)=>b.time.localeCompare(a.time))[0];if(first)show(D.recs.indexOf(first));
</script></body></html>
"""

if __name__ == "__main__":
    main()
