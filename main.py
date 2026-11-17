"""gta6-twitch-ccu-forecast-01 entry: rolling-midnight launch-day forecaster.

Forecasts hours 2..24 of a game's Twitch launch day (UTC) as five quantiles
each, anchored on the case's hour-1 print.

Method (fitted at run time from the case file's own comparables; nothing is
hard-coded from any practice launch):
  - Keep only "rolling-like" comparables: past launches whose release day
    actually rises after hour 1 (hour-1 print a real, post-unlock number, and
    an evening peak above hour 1). This drops simultaneous-global launches
    whose hour 1 is pre-unlock (ratios of 30x-2000x would poison the fit),
    flat simultaneous launches whose hour 1 is already the peak, and the
    early-access-contaminated / weak tiers.
  - Per forecast hour h, ordinary least squares of log(y_h / y_1) on
    log(y_1) across the rolling-like comparables. The launch-day ratio
    falls steeply with the hour-1 level (small launches rise ~5x-10x into
    the US evening; huge launches rise ~1.3x-1.7x), so the fit is keyed to
    this case's hour-1 print.
  - The effective hour-1 used in the regression is capped at the largest
    training hour-1: past that scale the linear slope would extrapolate to
    an evening below hour 1, which contradicts the rolling pattern.
  - Spread per hour is 0.9 x the regression's residual standard deviation,
    smoothed across neighbouring hours (13-point mean, +/-6 h), floored at
    0.10 log units. Quantiles are p1 * exp(mu_h + z_tau * s_h), z the standard
    normal's quantiles, rounded half-up to 2 decimals.

Reads only the case file it is given (hour 1 + pre-deadline history +
comparables): no future information, no network, no randomness, standard
library only. Deterministic: same case file in, same bytes out.
"""

import json
import math
import os
import sys
from pathlib import Path

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]

SPREAD_SCALE = 0.9
SPREAD_FLOOR = 0.10
MIN_TRAIN = 5
MAX_Q = 1e9


def round2(x):
    """x rounded to 2 decimals, half up (as JavaScript's Math.round does it)."""
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value == int(value) else value


def day_curve(comparable):
    """Release-day hourly viewers keyed by hour-of-day (0..23), or None."""
    try:
        day = comparable["day_start"][:10]
    except (KeyError, TypeError):
        return None
    vals = {}
    for h in comparable.get("hourly") or []:
        try:
            frm = h["from"]
            if frm[:10] != day:
                continue
            vals[int(frm[11:13])] = float(h["viewers"])
        except (KeyError, TypeError, ValueError):
            continue
    return vals


def is_rolling_like(comparable):
    """True when the launch's release day rises after hour 1 (rolling regime)."""
    unlock = str(comparable.get("unlock") or "").lower()
    if "early-access-contaminated" in unlock or "tier: weak" in unlock:
        return False
    if "grand theft auto vi" in str(comparable.get("name") or "").lower():
        return False  # the target's own pre-release history is not a launch
    v = day_curve(comparable)
    if not v or 0 not in v or not v[0] or v[0] <= 0:
        return False
    peak = max(v.values())
    if peak <= 0 or v[0] / peak < 0.05:
        return False  # hour 1 pre-unlock (simultaneous launch after midnight)
    evening = max((v.get(h, 0.0) for h in range(12, 24)), default=0.0)
    if evening < v[0] * 1.05:
        return False  # hour 1 already the peak (flat simultaneous launch)
    return True


def ols(xs, ys):
    """Least squares y = a + b*x; returns (a, b, residual_sd)."""
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx if sxx > 0 else 0.0
    a = my - b * mx
    resid = [y - (a + b * x) for x, y in zip(xs, ys)]
    sd = (sum(r * r for r in resid) / max(1, n - 2)) ** 0.5
    return a, b, sd


def fit_model(case):
    """Fit per-hour (mu_offset, spread) on the case's rolling-like comparables.

    Returns (predict, fallback_spread): predict(h, log_p1_eff) gives the
    median log-ratio for forecast hour h.
    """
    trains = []
    for comp in case.get("comparables") or []:
        if not is_rolling_like(comp):
            continue
        v = day_curve(comp)
        if v and v.get(0):
            trains.append(v)
    if len(trains) < MIN_TRAIN:
        # Relax: any non-excluded comparable with a real hour-1 print.
        trains = []
        for comp in case.get("comparables") or []:
            unlock = str(comp.get("unlock") or "").lower()
            if "early-access-contaminated" in unlock or "tier: weak" in unlock:
                continue
            v = day_curve(comp)
            if v and v.get(0):
                trains.append(v)
    if not trains:
        return None, 0.5
    p_max = max(v[0] for v in trains)
    params = {}
    for h in range(2, 25):
        xs, ys = [], []
        for v in trains:
            if v.get(h - 1):
                xs.append(math.log(v[0]))
                ys.append(math.log(v[h - 1] / v[0]))
        if len(xs) >= MIN_TRAIN:
            a, b, sd = ols(xs, ys)
            params[h] = (a, b, sd)
        else:
            # Too few points this hour: fall back to the median log-ratio.
            lr = sorted(ys)
            med = lr[len(lr) // 2] if lr else 0.0
            params[h] = (med, 0.0, 0.5)
    # Smooth the spread across neighbouring hours (13-point mean, +/-6 h).
    # Per-hour residual SDs come from ~19 launches, so each is noisy (~18%
    # sampling error); the true spread is a smooth hump over the day (low
    # overnight, high midday, lower in the evening), so borrowing strength
    # across hours cuts estimation noise. Width chosen by 20-fold
    # leave-one-out CV: LOO pinball 0.2657 at width 3 -> 0.2638 at width 13
    # (broad plateau 11-15; pooled single SD is worse again at 0.2656), and
    # the practice-4 mean improves 0.1799 -> 0.1778 at the same time.
    sds = [params[h][2] for h in range(2, 25)]
    smooth = []
    for i in range(len(sds)):
        lo = max(0, i - 6)
        hi = min(len(sds), i + 7)
        smooth.append(sum(sds[lo:hi]) / (hi - lo))

    def predict(h, log_p1_eff):
        a, b, _ = params[h]
        return a + b * log_p1_eff

    spreads = {h: max(SPREAD_FLOOR, smooth[h - 2] * SPREAD_SCALE)
               for h in range(2, 25)}
    return (predict, spreads, p_max), 0.5


def forecast_case(case):
    first = next((k for k in case.get("known") or [] if k.get("hour") == 1), None)
    if first is None:
        raise ValueError("case has no hour-1 print")
    p1 = max(1.0, float(first["viewers"]))
    fitted, _ = fit_model(case)
    hours = [row["hour"] for row in case.get("forecast") or []]
    if not hours:
        hours = list(range(2, 25))
    out_hours = []
    if fitted is None:
        # No usable comparables: persistence baseline (flat, widening spread).
        for h in hours:
            s = 0.15 * math.sqrt(h - 1)
            qs = [round2(p1 * math.exp(z * s)) for z in Z]
            out_hours.append({"hour": h, "q": [min(max(q, 0.01), MAX_Q) for q in qs]})
        return {"hours": out_hours}
    predict, spreads, p_max = fitted
    log_p1_eff = math.log(min(p1, p_max))
    for h in hours:
        mu = predict(h, log_p1_eff)
        s = spreads.get(h, 0.5)
        qs = []
        for z in Z:
            q = round2(p1 * math.exp(mu + z * s))
            qs.append(min(max(q, 0.01), MAX_Q))
        # Keep quantiles non-decreasing after rounding/clamping.
        for i in range(1, len(qs)):
            if qs[i] < qs[i - 1]:
                qs[i] = qs[i - 1]
        out_hours.append({"hour": h, "q": qs})
    return {"hours": out_hours}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
