"""RL market-maker for binary outcome markets — research-grounded, v3 (efficient).

Same sim as v2 (red-team-fixed: real behavioral surplus, monotonic fill model,
informed adverse selection that widening defends, no outcome look-ahead), but
rewritten for speed: Python `random` + Knuth Poisson + plain-list Q-table instead
of per-step scalar numpy calls (~10x faster). Tabular Q-learning is the right size
for thin outcome markets; deep RL (GPU) would overfit — see the RL thesis caveat.
"""
import math
import random

random.seed(7)

HALF = [0.010, 0.025, 0.050]        # tight / med / wide half-spread
SKEW = [-0.020, 0.0, 0.020]         # sell-lean (fade YES) / neutral / buy-lean
N_ACT = 9
INV_BINS, VPIN_BINS, REG = 7, 5, 2


def poisson(lam):
    """Knuth's algorithm — fast for small lambda (our flow rates ~1-3)."""
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= random.random()
        if p <= L:
            return k - 1


def clip(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


class MMEnv:
    def __init__(self, T=80, informed_rate=0.30, yes_overbet=1.4):
        self.T = T
        self.informed_rate = informed_rate
        self.yes_overbet = yes_overbet

    def reset(self):
        self.outcome = random.randint(0, 1)
        self.p = random.uniform(0.35, 0.65)
        self.t = 0
        self.inv = 0.0
        self.cash = 0.0
        self.flow = []
        return self._state()

    def _vpin(self):
        w = self.flow[-10:]
        if not w:
            return 0.0
        b = sum(x for x in w if x > 0)
        s = -sum(x for x in w if x < 0)
        return (b - s) / (b + s + 1e-9)

    def _state(self):
        inv_bin = int(clip(round(self.inv / 2) + 3, 0, INV_BINS - 1))
        vpin_bin = int(clip(round((self._vpin() + 1) * 2), 0, VPIN_BINS - 1))
        reg = 0 if 0.30 <= self.p <= 0.70 else 1
        return inv_bin * (VPIN_BINS * REG) + vpin_bin * REG + reg   # flattened index

    def step(self, action):
        half = HALF[action // 3]
        skew = SKEW[action % 3]
        mid = self.p
        bid = clip(mid - half + skew, 0.01, 0.99)
        ask = clip(mid + half + skew, 0.01, 0.99)
        tv = self.outcome
        w0 = self.cash + self.inv * mid

        n_ub = poisson(1.0 * self.yes_overbet)
        ub_fill = clip(1.0 - 3.0 * max(ask - mid, 0.0), 0.05, 1.0)
        n_ib = poisson(2.0) if (random.random() < self.informed_rate and tv == 1) else 0
        ib_fill = clip((tv - ask) / 0.15, 0.0, 1.0)
        sells = n_ub * ub_fill + n_ib * ib_fill

        n_us = poisson(1.0)
        us_fill = clip(1.0 - 3.0 * max(mid - bid, 0.0), 0.05, 1.0)
        n_is = poisson(2.0) if (random.random() < self.informed_rate and tv == 0) else 0
        is_fill = clip((bid - tv) / 0.15, 0.0, 1.0)
        buys = n_us * us_fill + n_is * is_fill

        self.cash += sells * ask - buys * bid
        self.inv += buys - sells
        self.flow.append((n_ub + n_ib) - (n_us + n_is))

        self.p = clip(self.p + 0.006 * (2 * tv - 1) + random.gauss(0, 0.03), 0.02, 0.98)
        self.t += 1
        done = self.t >= self.T
        val = tv if done else self.p
        w1 = self.cash + self.inv * val
        reward = (w1 - w0) - 0.003 * self.inv ** 2
        return self._state(), reward, done


N_STATES = INV_BINS * VPIN_BINS * REG


def train(episodes=50000, alpha=0.2, gamma=0.97):
    Q = [[0.0] * N_ACT for _ in range(N_STATES)]
    env = MMEnv()
    eps = 1.0
    for _ in range(episodes):
        s = env.reset()
        done = False
        while not done:
            if random.random() < eps:
                a = random.randrange(N_ACT)
            else:
                row = Q[s]; a = max(range(N_ACT), key=row.__getitem__)
            s2, r, done = env.step(a)
            best = 0.0 if done else max(Q[s2])
            Q[s][a] += alpha * (r + gamma * best - Q[s][a])
            s = s2
        eps = max(0.05, eps * 0.99985)
    return Q


def evaluate(policy, n=8000):
    env = MMEnv()
    tot = []
    for _ in range(n):
        s = env.reset()
        done = False
        while not done:
            s, _, done = env.step(policy(s))
        tot.append(env.cash + env.inv * env.outcome)
    m = sum(tot) / len(tot)
    var = sum((x - m) ** 2 for x in tot) / len(tot)
    sd = var ** 0.5
    return m, sd, sum(1 for x in tot if x > 0) / len(tot), m / (sd + 1e-9)


if __name__ == "__main__":
    import time
    t0 = time.time()
    print("v3 (efficient, red-team-fixed sim): training...")
    Q = train()
    med_neutral = 1 * 3 + 1
    tight_sell = 0 * 3 + 0
    pols = {
        "baseline(med,flat)": lambda s: med_neutral,
        "always-fade-YES": lambda s: tight_sell,
        "RL(learned)": lambda s: max(range(N_ACT), key=Q[s].__getitem__),
    }
    print(f"\n{'policy':<20}{'mean P&L':>10}{'std':>9}{'win%':>8}{'Sharpe':>9}")
    res = {}
    for name, pol in pols.items():
        res[name] = evaluate(pol)
        m, sd, w, sh = res[name]
        print(f"{name:<20}{m:>10.3f}{sd:>9.3f}{w*100:>7.1f}%{sh:>9.3f}")
    bl = res["baseline(med,flat)"][0]; rl = res["RL(learned)"][0]
    print(f"\nRL vs baseline: {rl-bl:+.3f} ({100*(rl-bl)/(abs(bl)+1e-9):+.0f}%)")
    names = [f"{['tight','med','wide'][a//3]:<5},{['SELL-lean','neutral','BUY-lean'][a%3]}" for a in range(N_ACT)]
    print("\nlearned policy vs buy-pressure (inv~0, interior):")
    for vb in range(VPIN_BINS):
        s = 3 * (VPIN_BINS * REG) + vb * REG + 0
        a = max(range(N_ACT), key=Q[s].__getitem__)
        print(f"  buy-pressure≈{vb/2-1:+.1f}: -> {names[a]}")
    print(f"\ntrained in {time.time()-t0:.0f}s")
