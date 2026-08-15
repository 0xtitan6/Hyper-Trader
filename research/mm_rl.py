"""RL market-maker for binary outcome markets — research-grounded, v4.

v4 changes over v3 (all principled; no outcome look-ahead, baseline untouched, still tabular):
  1. REWARD ALIGNED TO EVAL. v3 trained on (w1-w0) - 0.003*inv^2 with gamma=0.97; eval scored
     raw terminal (cash + inv*outcome). The dense increment (w1-w0) telescopes EXACTLY to terminal
     PnL (w starts at 0), so removing the inv^2 penalty and using gamma=1.0 makes Q(s,a) an unbiased
     estimate of expected terminal PnL — the exact quantity evaluate() scores. (inv^2 was a risk term
     that optimized a different objective than the scoreboard.)
  2. TIME-TO-RESOLUTION IN STATE. v3 state = inv x vpin x 2-regime (70 states); it could not tell
     t=5 from t=79, so no endgame inventory unwind was learnable. Add TBINS time bins (observable,
     NOT look-ahead). N_STATES = 7*5*2*TBINS.
  3. OPTIMISTIC INIT (Q0=0.5) to counter pessimistic-init under-exploration.
Tabular Q-learning stays the right size for thin outcome markets; deep RL would overfit.
"""
import math
import random

random.seed(7)

HALF = [0.010, 0.025, 0.050]        # tight / med / wide half-spread
SKEW = [-0.020, 0.0, 0.020]         # sell-lean (fade YES) / neutral / buy-lean
N_ACT = 9
INV_BINS, VPIN_BINS, REG, TBINS = 7, 5, 2, 5


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


def state_index(inv_bin, vpin_bin, reg, t_bin):
    """Single source of truth for the flattened tabular index."""
    return ((inv_bin * VPIN_BINS + vpin_bin) * REG + reg) * TBINS + t_bin


N_STATES = INV_BINS * VPIN_BINS * REG * TBINS


class MMEnv:
    def __init__(self, T=80, informed_rate=0.30, yes_overbet=1.4, inv_penalty=0.0):
        self.T = T
        self.informed_rate = informed_rate
        self.yes_overbet = yes_overbet
        self.inv_penalty = inv_penalty   # 0.0 => reward telescopes to raw terminal PnL (matches eval)

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
        # time-to-resolution bin — observable (agent knows the clock); NOT outcome look-ahead
        t_bin = int(clip(self.t * TBINS // self.T, 0, TBINS - 1))
        return state_index(inv_bin, vpin_bin, reg, t_bin)

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
        # inv_penalty defaults to 0 -> sum of rewards telescopes to terminal PnL (the eval metric)
        reward = (w1 - w0) - self.inv_penalty * self.inv ** 2
        return self._state(), reward, done


def train(episodes=80000, alpha=0.2, gamma=1.0, q0=0.5, informed_rate=0.30, inv_penalty=0.0):
    Q = [[q0] * N_ACT for _ in range(N_STATES)]
    env = MMEnv(informed_rate=informed_rate, inv_penalty=inv_penalty)
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


def evaluate(policy, n=8000, informed_rate=0.30, seed=None):
    """Evaluate on raw terminal PnL. If seed is given, the market draws are reproducible so
    two policies can be compared on IDENTICAL scenarios (paired, low-variance, fair)."""
    if seed is not None:
        random.seed(seed)
    env = MMEnv(informed_rate=informed_rate)
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
    return m, sd, sum(1 for x in tot if x > 0) / len(tot), m / (sd + 1e-9), tot


if __name__ == "__main__":
    import time
    t0 = time.time()
    print("v4 (reward-aligned, time-aware state, optimistic init): training...")
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
        m, sd, w, sh, _ = evaluate(pol, seed=7)   # same seed for all => identical scenarios
        res[name] = (m, sd, w, sh)
        print(f"{name:<20}{m:>10.3f}{sd:>9.3f}{w*100:>7.1f}%{sh:>9.3f}")
    bl = res["baseline(med,flat)"][0]; rl = res["RL(learned)"][0]
    print(f"\nRL vs baseline: {rl-bl:+.3f} ({100*(rl-bl)/(abs(bl)+1e-9):+.0f}%)")
    names = [f"{['tight','med','wide'][a//3]:<5},{['SELL-lean','neutral','BUY-lean'][a%3]}" for a in range(N_ACT)]
    print("\nlearned endgame behavior (inv HIGH, interior price), early vs late:")
    for tb in range(TBINS):
        s = state_index(5, 2, 0, tb)   # inv_bin 5 = long inventory, neutral vpin, interior
        a = max(range(N_ACT), key=Q[s].__getitem__)
        print(f"  t_bin {tb} ({'early' if tb==0 else 'late' if tb==TBINS-1 else 'mid'}): -> {names[a]}")
    print(f"\ntrained in {time.time()-t0:.0f}s")
