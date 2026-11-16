"""
자금 운용 전략 비교 (판 배당 ~2.0, 400판 ≈ 2년). 시작 1,000만 → 목표 1억.
전략 근거:
- 고정/비율 베팅: 기본
- 파롤리: 연승 시 이익 재투자 (현행)
- 대담한 베팅(bold play): Dubins & Savage (1965) 'How to Gamble If You Must' — 기대값이 음수인 게임에서
  '목표 도달 확률'을 최대화하는 최적 전략은 목표에 필요한 만큼 크게 거는 것(소액 반복은 최악)
- CPPI: Black & Perold (1992) — 지켜야 할 바닥(floor)을 정하고, 바닥 위 여유분(cushion)에 비례해서만 공격
- 분수 켈리: Kelly (1956), Thorp (2006), MacLean·Thorp·Ziemba (2010) — 엣지가 있을 때 장기 성장률 최적, 1/4~1/2로 위험 축소
"""
import numpy as np
rng = np.random.default_rng(7)
S, G, N, R, O = 10_000_000, 100_000_000, 400, 20000, 2.0
FLOOR = 5_000_000

def sim(ev, kind):
    p = (1 + ev) / O
    B = np.full(R, float(S)); st = np.zeros(R); ch = np.zeros(R); hit = np.zeros(R, bool); done = np.zeros(R, bool)
    for _ in range(N):
        live = (B > 1000) & ~done
        if kind == "고정 20만": s = np.full(R, 200_000.0)
        elif kind == "자금 2%": s = 0.02 * B
        elif kind == "파롤리3 기본2%": s = np.where(st > 0, ch, 0.02 * B)
        elif kind == "파롤리3 기본5%": s = np.where(st > 0, ch, 0.05 * B)
        elif kind == "대담한 베팅": s = (G - B) / (O - 1)
        elif kind == "CPPI(바닥500만,여유 25%)": s = 0.25 * np.maximum(B - FLOOR, 0)
        elif kind == "CPPI+파롤리3(여유10%)": s = np.where(st > 0, ch, 0.10 * np.maximum(B - FLOOR, 0))
        elif kind == "1/4 켈리": s = np.full(R, max(0, 0.25 * (p * O - 1) / (O - 1))) * B
        s = np.where(live, np.minimum(s, B), 0)
        w = rng.random(R) < p
        B = B + np.where(w, s * (O - 1), -s)
        if "파롤리" in kind:
            st = np.where(w & (s > 0), st + 1, 0); ch = np.where(w, s * O, 0); r = st >= 3; st[r] = 0
        hit |= B >= G; done |= B >= G   # 목표 도달 시 중단(익절)
    return hit.mean(), (B < FLOOR).mean(), (B < S * 0.1).mean(), np.median(B)

K = ["고정 20만", "자금 2%", "파롤리3 기본2%", "파롤리3 기본5%", "CPPI(바닥500만,여유 25%)", "CPPI+파롤리3(여유10%)", "1/4 켈리", "대담한 베팅"]
for ev in [-0.04, -0.01, 0.02, 0.05]:
    print(f"\n=== 판당 기대값 {ev*100:+.0f}% (배당 2.0, 400판) ===")
    print(f"  {'전략':24s} {'1억 도달':>8s} {'500만 미만':>9s} {'100만 미만':>9s} {'중앙값':>10s}")
    for k in K:
        h, f, z, m = sim(ev, k)
        print(f"  {k:24s} {h*100:7.1f}% {f*100:8.1f}% {z*100:8.1f}% {m/1e6:8.1f}백만")
