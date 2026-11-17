# Gate 0 Study — gta6-twitch-ccu-forecast-01

## What the judge rewards (one paragraph)
The score is mean pinball loss on the LOG scale over 23 hours x 5 quantiles
(2 x max(tau*d, (tau-1)*d), d = ln(actual) - ln(quantile)). On the log scale a
forecast whose five quantiles are equal scores exactly its mean log miss, so
the judge rewards two things at once: a median that tracks the true hour-by-hour
level (a 10% level error costs about 0.10 loss at the median quantile) and an
honest spread — too narrow and the outer quantiles get hammered when the truth
lands outside them, too wide and every quantile pays for the slack. Coverage
near the nominal 90% with the smallest spread that achieves it is what wins.
The house baseline (flat at hour 1, spread 0.15*sqrt(h-1)) scores 0.387 on
practice; the live dev board's top entry scores 0.146 and rank 20 scores
0.180, so the bar to be competitive is roughly 0.15-0.18 on practice, and a
prize needs beating the better house entry on the FINAL (GTA VI itself).

## What our entry must do to beat both house entries (one paragraph)
The house baseline is beatable by any forecaster that knows a launch day is
NOT flat: every rolling-midnight launch rises from its 00:00 UTC hour-1 into a
US prime-time evening peak, typically 1.5x-3x hour 1 and up to 9x for small
launches. The house model entry is a single fixed ratio curve applied to every
case (one answer, made once, replayed on hour 1's print), so it cannot adapt
to the case at hand; our entry must beat it by being case-adaptive — fitting
the launch-day shape from the case's own comparables at run time, keyed to
this case's hour-1 level, because the shape depends strongly on scale (see
below). It must also be hindsight-clean (only hour-1 + pre-deadline data),
deterministic, stdlib-only, and under 8 s per case.

## Input / output format (verified from kit + starter)
- Case: JSON schema makefun/twitch-ccu-case/v1. `known` holds hour 1's print
  (viewers, channels, reads); `forecast` lists hours 2..24; `history_hourly`
  is the launch's own points up to the checkpoint (end of hour 1);
  `comparables` is 38 past launches (42 in the final) with `hourly` points
  from 14 days before to 3 days after their release day, plus `unlock`
  text and `platforms`.
- Output: {"hours": [{"hour": h, "q": [q05,q25,q50,q75,q95]}, ...]}, exactly
  23 rows, hours 2..24 once each, no other key, each q finite, > 0, <= 1e9,
  non-decreasing, <= 65,536 bytes. Quantiles are q = p1 * exp(mu_h + z_tau*s_h),
  z = [-1.645,-0.674,0,0.674,1.645], rounded half-up to 2 decimals.
- Grader runs `python3 -P -s /bot/main.py`, one case at a time, /input/<id>.in
  -> /output/<id>.out; env MAKEFUN_INPUT_DIR / MAKEFUN_OUTPUT_DIR outside.
  Invalid case = scored as if every quantile equalled hour 1, no prize.

## What a launch day looks like (practice answers, verified)
Practice answers were recovered from SullyGnome (the same public source the
house used, 4 small requests via the reader; 926/926 history points match the
case files exactly, so the answers are trustworthy):
- p00 Wolverine, h1 23,357: dips to 0.78x at h4, then explodes to 9.09x at
  h21 (evening peak 212k). Smallest hour 1, steepest rise.
- p01 RDR2, h1 116,550: dips 0.72x, peak 3.17x at h18, ends 1.65x.
- p02 GoW Ragnarok, h1 269,517: dips 0.53x at h4, peak only 1.71x at h20.
  Biggest hour 1, flattest curve.
- p03 Spider-Man 2, h1 119,087: dips 0.37x at h12 (deep midday lull),
  peak 2.21x at h22.
Common shape: overnight dip (h2-h4, 0.4x-0.9x), flat morning, steady rise
from h12, evening peak h18-h22, gentle decay into h24. The diurnal wave is
driven by time zones: hour 1 is NZ/Australia only (rolling midnight unlock
~12 h earlier); the evening is US prime time.

## The key regularity: the ratio depends on hour-1 scale
Across the 38 comparables, log(y_h / y_1) falls steeply with log(hour 1):
evening (h20) ratio is ~11.5x for RE Requiem (h1 46k), ~2.4x for MH Wilds
(152k), ~1.3x for The Last of Us Part II (365k). Per-hour OLS of
log(ratio) on log(hour 1) gives evening slopes around -0.4 to -0.5. Mechanism:
for a small launch hour 1 is a quiet NZ/AU hour; for a huge launch hour 1 is
already a global event (people stay up, streamers live from NZ unlock), so
the evening adds proportionally less. This is the "OLS on log hour-1" that
the dev board's rank-1 title names.

## Rolling vs simultaneous: the comparables split in two
- Rolling-midnight launches (the GTA VI regime): hour 1 is a real print
  (h1/peak 0.08-0.75), evening peak 1.3x-11x hour 1. 16 of 38 comparables
  are rolling-like by data (explicit "rolling"/"midnight local" text OR
  h1/peak >= 0.05 with an evening peak >= 1.05x hour 1).
- Simultaneous-global launches with unlock AFTER 00:00 UTC (Black Myth
  02:00Z, Silksong 14:00Z, Battlefield 6 ~14:00Z): hour 1 is pre-unlock
  (~0-5k), ratios explode to 30x-2000x. Including them poisons any fit.
- Simultaneous with unlock AT/BEFORE midnight (Elden Ring PC 23:00Z,
  Cyberpunk 00:00Z): hour 1 is already the peak, ratios flat ~0.9x.
  Also excluded: they are a different regime, not a launch-day rise.
- Early-access-contaminated (9) and weak/F2P (2) are excluded by tier.
The filter is data-driven (h1/peak + evening rise), not text-only, so it
survives the final's 42-launch set.

## The house baseline, quantified (practice)
Flat at hour 1, spread 0.15*sqrt(h-1): p00 0.744, p01 0.287, p02 0.215,
p03 0.303, mean 0.3871 — exactly the rules' stated ~0.387, which validates
both the pinball implementation and the recovered practice answers. It is
worst exactly where the launch explodes (p00) and best where the launch is
flat (p02).

## Model chosen (validated by 20-fold leave-one-out CV, not by practice alone)
Per-hour OLS: log(y_h/y_1) = a_h + b_h * log(p1), fit at run time on the
rolling-like comparables in the case file; spread = 0.9 x residual SD,
smoothed across neighbouring hours, floor 0.10; effective p1 capped at the
largest training hour-1 (no extrapolation past the biggest comparable —
the linear slope would otherwise forecast an evening BELOW hour 1 for a
1M+ hour-1 launch, contradicting the rolling pattern). LOO over 20
rolling-like launches (16 comparables + 4 practice): baseline 0.425,
median-ratio 0.299, OLS 0.266, pooled amplitude x shape 0.282, kernel
local OLS 0.279-0.331, OLS + channels 0.294 (no gain), OLS + pre-peak
feature 0.266 (no gain). Practice-4 loss of the chosen model: 0.180
(p00 0.241, p01 0.151, p02 0.139, p03 0.189) vs baseline 0.387.
On the live dev board that is around rank 18-20 (rank 1: 0.146, rank 10:
0.167, rank 20: 0.180). It is a principled, generalising model, not tuned
to the 4 practice cases (spread scale 0.9 chosen by LOO, not by practice).

## What the practice data does NOT cover (honest doubt pass)
- GTA VI is the biggest launch ever: its hour 1 will likely be 500k-1.5M,
  far above the largest rolling comparable (365k, TLOU2). The ratio curve
  at that scale is an extrapolation; the cap keeps it sane (evening ~1.4x
  hour 1, TLOU2-like) but the truth could be flatter (Elden Ring-like
  ~0.9x, if hour 1 already captures the global event) or steeper.
- GTA VI is multiplatform (PS5 + Xbox at launch, PC later) and open-world
  Rockstar; the closest analogue is RDR2 (same publisher/genre), which is
  a practice case and WILL be in the final's comparables — good, but it is
  one launch from 2018, and Twitch was a different place then.
- No comparable had a same-day global premiere event like GTA VI's
  extended-look (2026-08-27) driving pre-release category attention, nor a
  launch this hyped; a launch-day surge (e.g. a celebrity stream, a
  record-breaking moment) could push the evening well above any fitted
  ratio, and no spread fitted on past launches covers a true black swan.
- The practice set has only 4 launches, all rolling, all PS5-or-PC
  story games; the final is one launch, so the practice mean is a noisy
  guide and the LOO spread (0.266) is the honest expectation, not 0.180.
- SullyGnome samples small categories sparsely (~every 12 h); the final's
  hour-1 print is a single hourly average, so a noisy hour-1 moves the
  whole forecast (everything is anchored on p1).
