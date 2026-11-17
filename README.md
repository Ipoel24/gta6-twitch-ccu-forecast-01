# gta6-twitch-ccu-forecast-01

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/Ipoel24/gta6-twitch-ccu-forecast-01/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/Ipoel24/gta6-twitch-ccu-forecast-01/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Forecasts Grand Theft Auto VI's launch-day Twitch viewers hour by hour for the make.fun gta6-twitch-ccu-forecast-01 competition. One program, `main.py` (Python 3.13, standard library only), reads one case from `/input/<id>.in` and writes `/output/<id>.out`: for each of hours 2-24 of the release day (UTC), five quantiles (5%, 25%, 50%, 75%, 95%) of that hour's concurrent viewers in the game's Twitch category. On the four practice launches it scores a mean pinball loss of 0.1778 on the log scale, against 0.3871 for the house baseline.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=89n82h5c&utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>

## The model

A launch day is not flat. Hour 1 (00:00-01:00 UTC) is New Zealand and
Australia only — a rolling-midnight unlock reaches them ~12 hours before
London and ~19 before Los Angeles — and the day rises into a US prime-time
evening peak. How far it rises depends on the launch's scale: small launches
rise 5x-10x from hour 1, huge launches only ~1.3x-1.7x.

`main.py` fits that shape at run time from the case file's own comparables:

1. Keep only rolling-like past launches — release days that actually rise
   after hour 1. Simultaneous-global launches are dropped: their hour 1 is
   either pre-unlock (ratios of 30x-2000x) or already the peak (flat ~0.9x),
   and either would poison the fit. Early-access-contaminated and weak tiers
   are dropped too.
2. Per forecast hour, ordinary least squares of log(y_h / y_1) on log(y_1)
   across the rolling-like comparables.
3. The hour-1 print used in the regression is capped at the largest training
   hour-1, so the fit never extrapolates to an evening below hour 1 for a
   launch bigger than anything in the training set.
4. Spread per hour is 0.9 x the regression's residual standard deviation,
   smoothed across neighbouring hours (13-point mean, +/-6 h), floored at 0.10 log units.

Quantiles are `p1 * exp(mu_h + z_tau * s_h)`, rounded half-up to 2 decimals.
No network, no randomness, no future information: the program reads only the
case file (hour 1 + pre-deadline history + comparables), so two runs on the
same case write byte-identical output.

## Validation

Scored locally on the four practice cases against the launches' recorded
hours (recovered from SullyGnome, the same public source the house used;
926/926 history points match the case files exactly):

| case | hour-1 print | this entry | house baseline |
| --- | --- | --- | --- |
| Marvel's Wolverine | 23,357 | 0.234 | 0.744 |
| Red Dead Redemption 2 | 116,550 | 0.152 | 0.287 |
| God of War Ragnarök | 269,517 | 0.139 | 0.215 |
| Marvel's Spider-Man 2 | 119,087 | 0.186 | 0.303 |
| **mean pinball loss (log scale)** | | **0.178** | **0.387** |

The model was chosen by 20-fold leave-one-out cross-validation over 20
rolling-like launches (not by tuning to the four practice cases): baseline
0.425, median-ratio 0.299, this OLS model 0.264. The spread smoothing width
(13-point mean, +/-6 h) was also chosen by LOO: 0.266 at width 3, 0.264 at
width 13 (broad plateau 11-15). Details in `STUDY.md`.

Built for the make.fun gta6-twitch-ccu-forecast-01 competition. MIT licensed.
