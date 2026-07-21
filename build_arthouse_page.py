# -*- coding: utf-8 -*-
"""
arthouse_final.csv → arthouse_report.html

대외 공유용 산업 현황 페이지. 특정 작품 검토 내용은 담지 않는다.
손익분기는 고정 상수 대신 열람자가 MG·P&A·정산단가를 입력해 실시간 계산한다.
  BEP 관객 = (수입 MG + P&A) ÷ 실정산 부금단가
입력값은 브라우저 안에서만 쓰이고 페이지에 저장되지 않는다.
"""
import os
import csv
import json
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "arthouse_final.csv")
OUT = os.path.join(BASE, "arthouse_report.html")

RERELEASE_GAP = 6
NDAY = 15

# 세그먼트에서 통째로 빼는 대상 (필터가 아니라 제외)
#  · 직배  : 글로벌 스튜디오 한국지사 배급작. 비직배 수입 시장을 보려는 목적이므로 제외.
#  · 청불 소규모: 청소년관람불가 + 개봉스크린 20개 미만.
#    성인물을 정확히 집어내는 규칙이 아니라 근사치다. 크로넨버그 '미래의 범죄들'(칸 경쟁,
#    16개관)처럼 성격이 다른 작품도 함께 빠진다. 되살릴 작품은 KEEP 에 제목을 넣는다.
ERO_SCREEN_MAX = 20
KEEP = set()

# 계산기 초기값 (열람자가 화면에서 바꿀 수 있다)
#
# 손익분기선을 하나 긋지 않는 이유 —
# 수입 MG는 작품·계약마다 편차가 커서 하한이 없다시피 하고, 실제 회수 여부는
# 계약 조건을 봐야만 알 수 있다. 반면 P&A 는 극장 개봉을 하는 이상 하한이 있다
# (최대한 아껴 5천만, 보통 1억, 1.5~2억이면 잘 쓴 편).
# 따라서 이 페이지는 '누가 회수했다'를 판정하지 않고,
# MG 를 0원으로 놓아도 P&A 조차 못 건진 구간 = 어떤 계약이어도 손실인 구간만 표시한다.
DEF_MG, DEF_PA, DEF_UNIT = 0, 5000, 4200   # 만원, 만원, 원


def load():
    rows, n_major, n_ero = [], 0, 0
    for r in csv.DictReader(open(SRC, encoding="utf-8-sig")):
        oy = int(r["개봉일"][:4])
        py = int(r["제작연도"]) if r["제작연도"].isdigit() else oy
        iv = lambda k: int(r[k]) if r.get(k) and r[k].strip() else 0
        fv = lambda k: float(r[k]) if r.get(k) and r[k].strip() else 0
        if r["영화명"] not in KEEP:
            if r["직배여부"] == "직배":
                n_major += 1
                continue
            if "청소년관람불가" in r["등급"] and iv("개봉스크린수") < ERO_SCREEN_MAX:
                n_ero += 1
                continue
        rows.append({
            "name": r["영화명"], "open": r["개봉일"],
            "nat": r["대표국적"], "gen": r["장르"], "dir": r["감독"], "dist": r["배급사"],
            "scr": iv("개봉스크린수"),
            "s0": iv("개봉일좌석수"), "r0": fv("개봉일좌석판매율"),
            "sw": iv("첫주말좌석수"), "rw": fv("첫주말좌석판매율"),
            "fw": iv("첫주관객"), "cum": iv("최종누적관객"),
            "mult": fv("배수"),
            "c": [iv(f"D{i}") for i in range(NDAY)],
            "re": (oy - py) >= RERELEASE_GAP,
        })
    rows.sort(key=lambda r: -r["cum"])
    print(f"  제외: 직배 {n_major}편, 청불·소규모 {n_ero}편")
    return rows


HTML = """<title>한국 아트하우스 외화 흥행 실적 · 2024–2026</title>
<style>
  :root{
    --ink:#14181B; --paper:#F1F3F2; --card:#FFF; --line:#DCE1DF; --muted:#6B7573;
    --accent:#1F6F5C; --alert:#A8452F; --grid:#E7EBE9;
    --shadow:0 1px 2px rgba(20,24,27,.05),0 4px 18px rgba(20,24,27,.04);
  }
  @media (prefers-color-scheme:dark){:root{
    --ink:#E5E9E7; --paper:#0E1312; --card:#161C1A; --line:#28302E; --muted:#8B9694;
    --accent:#4FA88F; --alert:#D4735A; --grid:#232B29; --shadow:none;
  }}
  :root[data-theme="dark"]{
    --ink:#E5E9E7; --paper:#0E1312; --card:#161C1A; --line:#28302E; --muted:#8B9694;
    --accent:#4FA88F; --alert:#D4735A; --grid:#232B29; --shadow:none;
  }
  :root[data-theme="light"]{
    --ink:#14181B; --paper:#F1F3F2; --card:#FFF; --line:#DCE1DF; --muted:#6B7573;
    --accent:#1F6F5C; --alert:#A8452F; --grid:#E7EBE9;
    --shadow:0 1px 2px rgba(20,24,27,.05),0 4px 18px rgba(20,24,27,.04);
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--paper);color:var(--ink);
    font-family:'Pretendard',-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Malgun Gothic','맑은 고딕',sans-serif;
    font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased}
  .wrap{max-width:1400px;margin:0 auto;padding:44px 22px 90px;display:flex;flex-direction:column;gap:34px}
  header{display:flex;flex-direction:column;gap:9px;border-bottom:2px solid var(--ink);padding-bottom:18px}
  .eyebrow{font-size:11.5px;letter-spacing:.15em;text-transform:uppercase;color:var(--accent);font-weight:700}
  h1{margin:0;font-size:clamp(25px,4vw,37px);font-weight:800;letter-spacing:-.022em;line-height:1.18;text-wrap:balance}
  .sub{color:var(--muted);font-size:13.5px;max-width:74ch;margin:0}
  .tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:11px}
  .tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:15px 17px;
    display:flex;flex-direction:column;gap:4px;box-shadow:var(--shadow)}
  .tile .k{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);font-weight:700}
  .tile .v{font-size:25px;font-weight:800;letter-spacing:-.025em;font-variant-numeric:tabular-nums}
  .tile .n{font-size:12px;color:var(--muted)}
  section{display:flex;flex-direction:column;gap:13px}
  h2{margin:0;font-size:16.5px;font-weight:700;letter-spacing:-.01em}
  h2 .hint{font-weight:400;color:var(--muted);font-size:13px;margin-left:8px;letter-spacing:0}
  .panel{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:19px;box-shadow:var(--shadow)}

  /* 손익분기 계산기 */
  .calc{display:grid;grid-template-columns:repeat(auto-fit,minmax(132px,1fr));gap:16px;align-items:end}
  .fld{display:flex;flex-direction:column;gap:5px}
  .fld label{font-size:11.5px;letter-spacing:.05em;color:var(--muted);font-weight:700}
  .fld input{padding:9px 11px;border:1px solid var(--line);border-radius:8px;background:var(--paper);
    color:var(--ink);font:inherit;font-size:15px;font-variant-numeric:tabular-nums;text-align:right;width:100%}
  .fld .u{font-size:11px;color:var(--muted)}
  .out{border-left:3px solid var(--alert);padding-left:15px;display:flex;flex-direction:column;gap:2px}
  .out .big{font-size:27px;font-weight:800;letter-spacing:-.025em;font-variant-numeric:tabular-nums;line-height:1.15}
  .out .cap{font-size:11.5px;letter-spacing:.05em;color:var(--muted);font-weight:700}
  .out .sm{font-size:12.5px;color:var(--muted);font-variant-numeric:tabular-nums}
  .out .sm b{color:var(--accent);font-size:14px}
  .out.sim{border-left-color:var(--muted)}
  .out.sim.plus{border-left-color:var(--accent)} .out.sim.plus .big{color:var(--accent)}
  .out.sim.minus{border-left-color:var(--alert)} .out.sim.minus .big{color:var(--alert)}
  .wcur{display:flex;gap:6px}
  .wcur input{flex:1;min-width:0}
  .wcur select{padding:9px 7px;border:1px solid var(--line);border-radius:8px;background:var(--paper);
    color:var(--ink);font:inherit;font-size:13px;font-weight:700;cursor:pointer}
  .outs{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));gap:18px;
    margin-top:18px;padding-top:16px;border-top:1px solid var(--line)}
  .formula{font-size:12px;color:var(--muted);border-top:1px solid var(--line);margin-top:15px;padding-top:11px}

  .dist{display:flex;flex-direction:column;gap:7px}
  .drow{display:grid;grid-template-columns:92px 1fr 96px;align-items:center;gap:11px;font-size:13px}
  .drow .lb{color:var(--muted);font-variant-numeric:tabular-nums;text-align:right}
  .bar{height:19px;background:var(--grid);border-radius:3px;overflow:hidden}
  .bar i{display:block;height:100%;background:var(--muted);border-radius:3px;transition:background .15s}
  .drow.under .bar i{background:var(--alert)}
  .drow.under .lb{color:var(--alert);font-weight:700}
  .drow .ct{font-variant-numeric:tabular-nums;color:var(--muted);font-size:12.5px}
  .thr{display:flex;align-items:center;gap:9px;margin:4px 0}
  .thr::before,.thr::after{content:"";flex:1;height:2px;background:var(--alert)}
  .thr span{font-size:11.5px;font-weight:700;color:var(--alert);white-space:nowrap;
    font-variant-numeric:tabular-nums}
  .lg{font-size:12.5px;color:var(--muted);margin-top:10px;border-top:1px solid var(--line);padding-top:10px}
  .lg b{color:var(--accent)}

  .ctl{display:flex;gap:9px;flex-wrap:wrap;align-items:center}
  input[type=search]{flex:1 1 250px;min-width:190px;padding:9px 13px;border:1px solid var(--line);
    border-radius:8px;background:var(--card);color:var(--ink);font:inherit;font-size:14px}
  input:focus-visible,button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
  button.tog{padding:9px 13px;border:1px solid var(--line);border-radius:8px;background:var(--card);
    color:var(--muted);font:inherit;font-size:13px;font-weight:600;cursor:pointer}
  button.tog[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:var(--card)}
  .count{font-size:13px;color:var(--muted);font-variant-numeric:tabular-nums;margin-left:auto}

  .tw{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--card);box-shadow:var(--shadow)}
  table{border-collapse:collapse;width:100%;font-size:13px}
  th,td{padding:8px 11px;text-align:left;white-space:nowrap;border-bottom:1px solid var(--line);vertical-align:top}
  thead th{position:sticky;top:0;background:var(--card);z-index:2;font-size:11px;letter-spacing:.05em;
    color:var(--muted);font-weight:700;cursor:pointer;user-select:none;border-bottom:2px solid var(--line);
    white-space:nowrap}
  thead th:hover{color:var(--ink)} thead th.on{color:var(--accent)}
  thead th.on::after{content:attr(data-a);margin-left:4px}
  td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
  tbody tr:hover{background:color-mix(in srgb,var(--accent) 7%,transparent)}
  tbody tr:last-child td{border-bottom:none}
  .nm{font-weight:600;white-space:normal;min-width:170px;max-width:230px}
  .meta{color:var(--muted);font-size:11.5px}
  /* 배급사 셀. 분포 차트의 .dist 와 이름이 겹치면 display:flex 가 흘러들어와
     td 가 테이블 레이아웃에서 빠지고 행 경계선이 끊긴다. 반드시 다른 이름을 쓴다. */
  td.dstr{max-width:140px;white-space:normal;font-size:11.5px;color:var(--muted)}
  .cum{font-weight:700} .under{color:var(--alert)}
  .lg .u,.out .sm b{color:var(--alert)}
  .pill{display:inline-block;padding:0 6px;border-radius:99px;font-size:10.5px;font-weight:700;
    border:1px solid currentColor;margin-left:5px;color:var(--muted)}
  .spark{display:block}
  tr.mark td{background:color-mix(in srgb,var(--alert) 10%,var(--card));border-top:2px solid var(--alert);
    border-bottom:2px solid var(--alert);font-weight:700;color:var(--alert);white-space:normal;
    font-size:13px;line-height:1.55}
  tr.mark span{display:block;font-weight:400;color:var(--muted);font-size:11.5px;margin-top:3px}
  footer{color:var(--muted);font-size:12.5px;border-top:1px solid var(--line);padding-top:15px}
  footer code{background:var(--grid);padding:1px 5px;border-radius:4px;font-size:11.5px}
  @media (max-width:640px){.wrap{padding:26px 13px 60px}.drow{grid-template-columns:74px 1fr 68px}}
</style>

<div class="wrap">
  <header>
    <div class="eyebrow">KOBIS 통합전산망 기반 · 2024–2026</div>
    <h1>한국 아트하우스 외화 흥행 실적</h1>
    <p class="sub">2024년 1월 ~ 2026년 4월 개봉, KOBIS에서 다양성영화 × 외국영화로 분류된 __N__편.
      직배(글로벌 스튜디오 한국지사 배급)와 청소년관람불가 중 개봉 20개관 미만은 제외해
      비직배 수입 시장만 남겼습니다. 재개봉·구작(개봉연도 − 제작연도 ≥ 6년)은 기본 숨김입니다.</p>
  </header>

  <div class="tiles">__TILES__</div>

  <section>
    <h2>얼마를 써야 본전인가<span class="hint">비용을 넣으면 그 돈조차 못 번 영화가 몇 편인지 나옵니다</span></h2>
    <div class="panel">
      <div class="calc">
        <div class="fld"><label for="pa">P&amp;A</label>
          <input id="pa" type="number" min="0" step="500" value="__PA__" inputmode="numeric">
          <span class="u">만원 · 최소 5,000 / 보통 10,000 / 잘 쓰면 15,000~20,000</span></div>
        <div class="fld"><label for="mg">수입 MG</label>
          <div class="wcur">
            <input id="mg" type="number" min="0" step="1000" value="__MG__" inputmode="numeric">
            <select id="cur" aria-label="통화">
              <option value="USD">USD</option>
              <option value="EUR">EUR</option>
              <option value="KRW">만원</option>
            </select>
          </div>
          <span class="u" id="mgu">0으로 두면 가장 보수적인 하한</span></div>
        <div class="fld" id="fxfld"><label for="fx">적용 환율</label>
          <input id="fx" type="number" min="1" step="10" value="1500" inputmode="numeric">
          <span class="u" id="fxu">원 / 1 USD</span></div>
        <div class="fld"><label for="up">실정산 부금단가</label>
          <input id="up" type="number" min="1" step="100" value="__UNIT__" inputmode="numeric">
          <span class="u">원 / 관객 1명</span></div>
        <div class="fld"><label for="au">예상 관객수</label>
          <input id="au" type="number" min="0" step="1000" value="__AUD__" inputmode="numeric">
          <span class="u">명 · 이 성적일 때 손익</span></div>
      </div>
      <div class="outs">
        <div class="out">
          <span class="cap">이만큼은 들어야 본전</span>
          <span class="big" id="obep">–</span>
          <span class="sm" id="orate">–</span>
        </div>
        <div class="out sim" id="simbox">
          <span class="cap">그때 전체 손익</span>
          <span class="big" id="osim">–</span>
          <span class="sm" id="osimn">–</span>
        </div>
        <div class="out sim" id="relbox">
          <span class="cap">개봉 실익 · 개봉 안 하는 경우 대비</span>
          <span class="big" id="orel">–</span>
          <span class="sm" id="oreln">–</span>
        </div>
      </div>
      <div class="formula">
        수입가(MG)는 작품마다 천차만별이라 누가 남겼는지는 실제 계약을 봐야 압니다.
        하지만 P&amp;A는 극장 개봉을 하는 이상 최소한 들어가는 돈이 있습니다.
        그래서 이 페이지는 <b>영화를 공짜로 사왔다고 쳐도 그 P&amp;A조차 극장에서 못 번 영화</b>만 붉게 표시합니다.
        수입가를 아신다면 위 칸에 넣어보세요. 입력값은 이 브라우저에만 있고 저장되지 않습니다.        <br><br><b>개봉이 이득인지는 MG와 무관합니다.</b>
        개봉을 안 하면 손실은 수입 MG 그대로이고, 개봉하면 거기에 P&amp;A가 더해지고 부금이 들어옵니다.
        양쪽에서 MG가 상쇄되므로 <b>부금이 P&amp;A를 넘느냐</b>만 남습니다.
        그래서 개봉 분기점은 P&amp;A ÷ 부금단가이고, 수입가를 얼마에 샀든 이 선은 같습니다.
      </div>
    </div>
  </section>

  <section>
    <h2>관객수 구간별 분포<span class="hint">붉은 구간이 비용조차 못 번 영화들입니다</span></h2>
    <div class="panel">
      <div class="dist" id="dist"></div>
      <div class="lg" id="distlg"></div>
    </div>
  </section>

  <section>
    <h2>전체 랭킹<span class="hint">열 제목을 눌러 정렬 · 막대는 개봉일부터 14일간 일별 관객</span></h2>
    <div class="ctl">
      <input type="search" id="q" placeholder="영화명 · 감독 · 국가 · 장르 · 배급사 검색" aria-label="검색">
      <button class="tog" id="tre" aria-pressed="false">재개봉 포함</button>
      <button class="tog" id="tbep" aria-pressed="false">못 번 영화만</button>
      <span class="count" id="ct"></span>
    </div>
    <div class="tw">
      <table>
        <thead><tr>
          <th class="num" data-k="rank">#</th>
          <th data-k="name">영화</th>
          <th data-k="open">개봉일</th>
          <th data-k="nat">국가</th>
          <th data-k="dist">배급사</th>
          <th class="num" data-k="scr">개봉<br>스크린</th>
          <th class="num" data-k="s0">개봉일<br>좌석수</th>
          <th class="num" data-k="r0">개봉일<br>판매율</th>
          <th class="num" data-k="sw">첫주말<br>좌석수</th>
          <th class="num" data-k="rw">첫주말<br>판매율</th>
          <th data-k="rank">D+0 → D+14</th>
          <th class="num" data-k="fw">첫주<br>관객</th>
          <th class="num" data-k="cum">최종<br>누적</th>
          <th class="num" data-k="cum">부금<br>환산</th>
          <th class="num" data-k="mult">배수</th>
        </tr></thead>
        <tbody id="tb"></tbody>
      </table>
    </div>
  </section>

  <footer>
    출처 영화진흥위원회 영화관입장권통합전산망(KOBIS) · 수집 __DATE__<br>
    첫주 관객은 개봉일~D+6, 첫 주말은 개봉 후 처음 오는 금·토·일 구간입니다.
    좌석판매율은 해당 구간 관객수 ÷ 좌석수로 직접 계산했습니다.
    배수는 최종 누적 ÷ 첫주 관객으로, 값이 클수록 개봉 후 입소문으로 확산된 작품입니다.
    좌석 데이터가 제공되지 않는 일부 소규모 상영은 <code>–</code>로 표시했습니다.<br>부금 환산은 관객수 × 부금단가로 계산한 <b>참고용 추정치</b>이며 실제 정산액이 아닙니다. 개별 작품의 손익은 수입 MG·P&amp;A 등 계약 조건에 따라 달라지므로 이 페이지만으로 판단할 수 없습니다.
  </footer>
</div>

<script>
const D=__DATA__;
const tb=document.getElementById('tb'), q=document.getElementById('q'), ct=document.getElementById('ct'),
      tre=document.getElementById('tre'), tbep=document.getElementById('tbep'),
      mg=document.getElementById('mg'), pa=document.getElementById('pa'), up=document.getElementById('up'),
      obep=document.getElementById('obep'), orate=document.getElementById('orate'),
      au=document.getElementById('au'),
      osim=document.getElementById('osim'), osimn=document.getElementById('osimn'),
      simbox=document.getElementById('simbox'),
      orel=document.getElementById('orel'), oreln=document.getElementById('oreln'),
      relbox=document.getElementById('relbox'),
      dist=document.getElementById('dist'), distlg=document.getElementById('distlg');
let sortK='rank', sortA=true, showRe=false, onlyBep=false, BEP=0;
const fmt=n=>n?Math.round(n).toLocaleString('ko-KR'):'–';
const esc=s=>String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));


// 수입 MG는 달러·유로로 계약하는 경우가 많아 통화를 고를 수 있게 둔다.
// 환율은 수시로 바뀌므로 고정하지 않고 입력값으로 두되 기본값만 채워둔다.
const cur=document.getElementById('cur'), fx=document.getElementById('fx'),
      fxfld=document.getElementById('fxfld'), mgu=document.getElementById('mgu'),
      fxu=document.getElementById('fxu');
const SYM={USD:'$',EUR:'€'}, FXDEF={USD:1500,EUR:1600};
function mgWon(){
  const v=Number(mg.value)||0;
  return cur.value==='KRW' ? v*10000 : v*(Number(fx.value)||0);
}
function mgLabel(){
  const v=Number(mg.value)||0;
  return cur.value==='KRW' ? `MG ${fmt(v)}만`
                           : `MG ${SYM[cur.value]}${fmt(v)}(${fmt(mgWon()/10000)}만)`;
}
function syncCur(){
  const krw=cur.value==='KRW';
  fxfld.style.display=krw?'none':'';
  if(!krw) fxu.textContent=`원 / 1 ${cur.value}`;
  mgu.textContent=(krw?'만원':cur.value)+' · 0으로 두면 가장 보수적인 하한';
}

const BUCKETS=[[200000,1e9,'20만+'],[100000,200000,'10만–20만'],[50000,100000,'5만–10만'],
  [30000,50000,'3만–5만'],[20000,30000,'2만–3만'],[10000,20000,'1만–2만'],
  [5000,10000,'5천–1만'],[1000,5000,'1천–5천'],[0,1000,'1천 미만']];

// 입력 조건을 사람 말로 풀어 쓴다. MG 0원이면 '공짜로 사왔어도' 라는 표현이 성립한다.
function costPhrase(){
  const w=mgWon(), p=Number(pa.value)||0;
  return w===0
    ? `영화를 공짜로 사왔어도 P&A ${fmt(p)}만원`
    : `${mgLabel()} + P&A ${fmt(p)}만 = ${fmt(w/10000+p)}만원`;
}

function calcBep(){
  const tot=mgWon()+(Number(pa.value)||0)*10000;
  const u=Number(up.value)||0;
  BEP = u>0 ? tot/u : 0;
  const base=D.filter(d=>!d.re);
  const k=base.filter(d=>d.cum<BEP).length;   // 아래쪽(확실히 못 번 쪽)을 센다
  obep.textContent = BEP>0 ? fmt(BEP)+'명' : '–';
  orate.innerHTML = BEP>0
    ? `${costPhrase()}은 못 벌었을 작품 <b>${k}편 / ${base.length}편 (${(100*k/base.length).toFixed(1)}%)</b>`
    : '부금단가를 입력하세요';
}

const compact=n=>n>=10000?String(+(n/10000).toFixed(1)).replace(/\\.0$/,'')+'만':fmt(n);


// 예상 관객수를 넣으면 그 지점의 손익을 계산한다.
//   부금 = 관객수 × 부금단가,  손익 = 부금 − (MG + P&A)
function simulate(base){
  const a=Number(au.value)||0, u=Number(up.value)||0;
  const tot=mgWon()+(Number(pa.value)||0)*10000;
  const rev=a*u, pl=rev-tot;
  osim.textContent=(pl>=0?'+':'−')+fmt(Math.abs(pl)/10000)+'만원';
  simbox.classList.toggle('plus',pl>=0);
  simbox.classList.toggle('minus',pl<0);
  const better=base.filter(d=>d.cum>=a).length;
  const pct=base.length?100*better/base.length:0;
  osimn.innerHTML=`부금 ${fmt(rev/10000)}만원 · 이 성적을 넘긴 작품 `
    +`<b>${better}편 / ${base.length}편 (상위 ${pct.toFixed(0)}%)</b>`;

  // 개봉 여부 판단 — 개봉 안 하면 손실은 MG 그대로, 개봉하면 -MG-P&A+부금.
  // 양쪽에서 MG가 상쇄되므로 부금이 P&A 를 넘는지만 보면 된다(MG 무관).
  const paw=(Number(pa.value)||0)*10000;
  const relGain=rev-paw, relNeed=u>0?paw/u:0;
  orel.textContent=(relGain>=0?'+':'−')+fmt(Math.abs(relGain)/10000)+'만원';
  relbox.classList.toggle('plus',relGain>=0);
  relbox.classList.toggle('minus',relGain<0);
  oreln.innerHTML=`개봉 분기 <b>${fmt(relNeed)}명</b> · 이보다 적으면 `
    +`<b>개봉 안 하고 MG만 손실 보는 편이 이득</b>`;
}

function drawDist(){
  const base=D.filter(d=>!d.re);
  // 입력값이 구간 한가운데를 지나면 그 구간을 정확히 둘로 쪼갠다.
  // 그래야 기준선이 실제 위치에 그어지고, 아래쪽만 붉게 칠할 수 있다.
  let bs=BUCKETS.map(([lo,hi,lb])=>({lo,hi,lb}));
  if(BEP>0){
    const i=bs.findIndex(b=>b.lo<BEP&&BEP<b.hi);
    if(i>=0){
      const b=bs[i];
      bs.splice(i,1,
        {lo:BEP,hi:b.hi,lb:b.hi>=1e9?compact(BEP)+'+':compact(BEP)+'–'+compact(b.hi)},
        {lo:b.lo,hi:BEP,lb:compact(b.lo)+'–'+compact(BEP)});
    }
  }
  const cnt=bs.map(b=>base.filter(d=>d.cum>=b.lo&&d.cum<b.hi).length);
  const mx=Math.max(...cnt,1);
  dist.innerHTML=bs.map((b,i)=>{
    const line=(BEP>0&&i>0&&bs[i-1].lo>=BEP&&b.hi<=BEP)
      ? `<div class="thr"><span>${fmt(BEP)}명</span></div>` : '';
    return line+`<div class="drow ${BEP>0&&b.hi<=BEP?'under':''}"><span class="lb">${b.lb}</span>
     <span class="bar"><i style="width:${Math.max(2,Math.round(100*cnt[i]/mx))}%"></i></span>
     <span class="ct">${cnt[i]}편</span></div>`;
  }).join('');
  const med=[...base].sort((a,b)=>a.cum-b.cum)[Math.floor(base.length/2)];
  distlg.innerHTML=`중앙값 <b class="u">${fmt(med.cum)}명</b> (부금 환산 ${fmt(med.cum*(Number(up.value)||0)/10000)}만원)`
    + ` · 5천 명 미만 ${base.filter(d=>d.cum<5000).length}편`
    + (BEP>0?` · <span class="u">선 아래 = ${costPhrase()}도 극장에서 못 번 영화</span>`:'');
}

function spark(c){
  const w=104,h=26,mx=Math.max(...c,1),n=c.length,bw=w/n;
  let b='';
  for(let i=0;i<n;i++){
    const bh=Math.max(1,Math.round(c[i]/mx*(h-3)));
    b+=`<rect x="${(i*bw).toFixed(1)}" y="${h-bh}" width="${(bw-1.1).toFixed(1)}" height="${bh}" rx="0.7"/>`;
  }
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"
    fill="currentColor" opacity=".72">${b}</svg>`;
}

function view(){
  let r=D.filter(d=>showRe||!d.re);
  if(onlyBep&&BEP>0) r=r.filter(d=>d.cum<BEP);
  const s=q.value.trim().toLowerCase();
  if(s) r=r.filter(d=>(d.name+' '+d.dir+' '+d.nat+' '+d.gen+' '+d.dist).toLowerCase().includes(s));
  r.forEach((d,i)=>d.rank=i+1);
  const dir=sortA?1:-1;
  r.sort((a,b)=>{const x=a[sortK],y=b[sortK];
    return typeof x==='string'?x.localeCompare(y,'ko')*dir:(x-y)*dir;});
  return r;
}

function draw(){
  const r=view(); let html='', marked=false;
  const banded=(sortK==='cum'||sortK==='rank');
  const desc=(sortK==='cum'&&!sortA)||(sortK==='rank'&&sortA);
  for(const d of r){
    if(banded&&desc&&!marked&&BEP>0&&d.cum<BEP){
      html+=`<tr class="mark"><td colspan="15">여기 아래는 ${costPhrase()}조차 극장에서 못 번 영화들
        — ${fmt(BEP)}명 미만<br>
        <span>위쪽이라고 남는 장사였다는 뜻은 아닙니다. 실제 수입가를 알아야 알 수 있습니다.</span></td></tr>`;
      marked=true;
    }
    const under=BEP>0&&d.cum<BEP;
    html+=`<tr>
      <td class="num meta">${d.rank}</td>
      <td class="nm">${esc(d.name)}${d.re?'<span class="pill">재개봉</span>':''}
        <div class="meta">${esc([d.dir,d.gen].filter(Boolean).join(' · '))||'&nbsp;'}</div></td>
      <td class="meta">${d.open}</td>
      <td class="meta">${esc(d.nat)||'–'}</td>
      <td class="dstr">${esc(d.dist)||'–'}</td>
      <td class="num">${fmt(d.scr)}</td>
      <td class="num">${fmt(d.s0)}</td>
      <td class="num meta">${d.r0?d.r0.toFixed(1)+'%':'–'}</td>
      <td class="num">${fmt(d.sw)}</td>
      <td class="num meta">${d.rw?d.rw.toFixed(1)+'%':'–'}</td>
      <td>${spark(d.c)}</td>
      <td class="num">${fmt(d.fw)}</td>
      <td class="num cum ${under?'under':''}">${fmt(d.cum)}</td>
      <td class="num meta">${fmt(d.cum*(Number(up.value)||0)/10000)}만</td>
      <td class="num meta">${d.mult?d.mult.toFixed(1)+'×':'–'}</td>
    </tr>`;
  }
  tb.innerHTML=html;
  const nb=BEP>0?r.filter(d=>d.cum<BEP).length:0;
  ct.textContent=`${r.length}편 표시`+(BEP>0?` · 못 번 영화 ${nb}편 (${r.length?(100*nb/r.length).toFixed(1):0}%)`:'');
}

function refresh(){ calcBep(); simulate(D.filter(d=>!d.re)); drawDist(); draw(); }

document.querySelectorAll('thead th').forEach(th=>{
  th.addEventListener('click',()=>{
    const k=th.dataset.k;
    if(sortK===k) sortA=!sortA;
    else{sortK=k; sortA=['rank','name','open','nat','dist'].includes(k);}
    document.querySelectorAll('thead th').forEach(o=>{o.classList.remove('on');o.removeAttribute('data-a');});
    th.classList.add('on'); th.setAttribute('data-a',sortA?'↑':'↓');
    draw();
  });
});
[mg,pa,up,au,fx].forEach(el=>el.addEventListener('input',refresh));
cur.addEventListener('change',()=>{if(FXDEF[cur.value])fx.value=FXDEF[cur.value];syncCur();refresh();});
q.addEventListener('input',draw);
tre.addEventListener('click',()=>{showRe=!showRe;tre.setAttribute('aria-pressed',showRe);
  tre.textContent=showRe?'재개봉 포함됨':'재개봉 포함';refresh();});
tbep.addEventListener('click',()=>{onlyBep=!onlyBep;tbep.setAttribute('aria-pressed',onlyBep);draw();});
syncCur();
refresh();
</script>
"""


def main():
    rows = load()
    live = [r for r in rows if not r["re"]]
    c = sorted(r["cum"] for r in live)
    n = len(c)
    ns = sum(1 for r in live if r["sw"])

    tiles = [
        ("분석 대상", f"{n}편", "비직배 신작 외화"),
        ("중앙값", f"{c[n//2]:,}", "절반이 이 아래"),
        ("상위 10%", f"{c[int(n*0.90)]:,}", "상위 25%는 " + f"{c[int(n*0.75)]:,}명"),
        ("5천 명 미만", f"{sum(1 for x in c if x < 5000)}편",
         f"전체의 {round(100*sum(1 for x in c if x<5000)/n)}%"),
        ("최고 기록", f"{c[-1]:,}", live[0]["name"]),
        ("좌석 데이터", f"{ns}편", f"{round(100*ns/n)}% 확보"),
    ]
    th = "".join(f'<div class="tile"><span class="k">{t[0]}</span>'
                 f'<span class="v">{t[1]}</span><span class="n">{t[2]}</span></div>' for t in tiles)

    keys = ("name", "open", "nat", "gen", "dir", "dist", "scr", "s0", "r0",
            "sw", "rw", "fw", "cum", "mult", "c", "re")
    data = [{k: r[k] for k in keys} for r in rows]
    html = (HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
                .replace("__TILES__", th).replace("__N__", str(n))
                .replace("__MG__", str(DEF_MG)).replace("__PA__", str(DEF_PA))
                .replace("__UNIT__", str(DEF_UNIT)).replace("__AUD__", str(c[n//2]))
                .replace("__DATE__", datetime.date.today().strftime("%Y-%m-%d")))
    open(OUT, "w", encoding="utf-8").write(html)
    print(f"완료: {OUT} (표시 {len(rows)}편 / 신작 {n}편 / 좌석 {ns}편)")


if __name__ == "__main__":
    main()
