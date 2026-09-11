"""Calibrated RL sweep — close the loop between the synthetic sim and the real tape.

The tape replay (maker_replay.py) shows adverse selection is only ~2.6% of spread
income on real HL outcome flow -> the TRUE informed_rate is far below the 0.30 the
sim assumed (where the maker lost). Re-run the exact same RL/baseline at lower,
data-plausible informed rates and confirm the maker turns profitable. Reuses the
validated MMEnv/poisson from mm_rl.py unchanged.
"""
import random
import time
from mm_rl import MMEnv, N_ACT, N_STATES

random.seed(7)


def train(informed_rate, episodes=40000, alpha=0.2, gamma=0.97):
    Q = [[0.0] * N_ACT for _ in range(N_STATES)]
    env = MMEnv(informed_rate=informed_rate)
    eps = 1.0
    for _ in range(episodes):
        s = env.reset(); done = False
        while not done:
            a = random.randrange(N_ACT) if random.random() < eps else max(range(N_ACT), key=Q[s].__getitem__)
            s2, r, done = env.step(a)
            Q[s][a] += alpha * (r + (0.0 if done else gamma * max(Q[s2])) - Q[s][a])
            s = s2
        eps = max(0.05, eps * 0.99985)
    return Q


def evaluate(informed_rate, policy, n=6000):
    env = MMEnv(informed_rate=informed_rate)
    tot = []
    for _ in range(n):
        s = env.reset(); done = False
        while not done:
            s, _, done = env.step(policy(s))
        tot.append(env.cash + env.inv * env.outcome)
    m = sum(tot) / len(tot)
    sd = (sum((x - m) ** 2 for x in tot) / len(tot)) ** 0.5
    return m, sd, sum(1 for x in tot if x > 0) / len(tot)


if __name__ == "__main__":
    t0 = time.time()
    med = 1 * 3 + 1
    print(f"{'informed_rate':>13} {'baseline':>10} {'RL':>10} {'RL win%':>9}")
    for ir in (0.30, 0.15, 0.08, 0.03):
        Q = train(ir)
        rl_pol = lambda s: max(range(N_ACT), key=Q[s].__getitem__)
        bm, _, _ = evaluate(ir, lambda s: med)
        rm, _, rw = evaluate(ir, rl_pol)
        flag = "MAKER PROFITABLE" if rm > 0 else "loses"
        print(f"{ir:>13.2f} {bm:>10.3f} {rm:>10.3f} {rw*100:>8.1f}%   {flag}")
    print(f"\n(real-tape adverse selection ~2.6% of spread => true informed_rate ~0.03-0.08 band)")
    print(f"swept in {time.time()-t0:.0f}s")
