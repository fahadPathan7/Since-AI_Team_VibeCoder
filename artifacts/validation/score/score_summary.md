# Score summary

- Scorer version: 0.1.1
- Schema version: 1.0
- Submission: forecast_validation.csv
- Actuals: actuals_validation.csv
- Spike margin: 50.00 EUR/MWh
- Rows in submission: 26880
- Rows scored (price metrics): 26700; skipped (no actual): 180
- Rows scored (exceptional prices): 26700
- Rows scored (direction): 26700

## Overall results

| Metric | Value | Use |
|---|---|---|
| MAE (p50) | 42.2885 | Level 1: accuracy |
| Pinball loss p10 | 7.2212 | |
| Pinball loss p90 | 16.5961 | |
| Mean pinball loss p10 and p90 | 11.9086 | Level 1: calibration |
| P10-P90 coverage | 0.7901 | supporting metric (target about 0.80) |
| Brier p_spike_high | 0.0990 | |
| Brier p_spike_low | 0.0854 | |
| Mean Brier, exceptional prices | 0.0922 | Level 1: exceptional prices |
| Three-class Brier, direction | 0.3987 | Level 1: direction |
| Pinball loss p50 | 21.1443 | for information |
| Observed share of high / low quarter-hours | 0.1213 / 0.1296 | for information |
| Baseline MAE (p50) | n/a | for information |
| MAE difference vs baseline (team - baseline) | n/a | for information |
| MAE ratio vs baseline (team / baseline) | n/a | for information |

## Results by forecast horizon

| Hour | Steps | Rows | MAE | Pinball p10/p90 mean | Coverage | Brier spikes | Brier direction |
|---|---|---|---|---|---|---|---|
| 1 | 1-4 | 2688 | 39.4164 | 11.0767 | 0.8121 | 0.0835 | 0.3723 |
| 2 | 5-8 | 2684 | 40.8821 | 11.4239 | 0.8018 | 0.0864 | 0.3895 |
| 3 | 9-12 | 2680 | 41.7302 | 11.6964 | 0.7884 | 0.0899 | 0.3977 |
| 4 | 13-16 | 2676 | 42.3442 | 11.8884 | 0.7885 | 0.0926 | 0.3989 |
| 5 | 17-20 | 2672 | 42.4620 | 11.9298 | 0.7878 | 0.0927 | 0.3991 |
| 6 | 21-24 | 2668 | 42.8158 | 12.0316 | 0.7837 | 0.0943 | 0.4015 |
| 7 | 25-28 | 2664 | 43.0864 | 12.1197 | 0.7887 | 0.0949 | 0.4030 |
| 8 | 29-32 | 2660 | 43.2779 | 12.2336 | 0.7861 | 0.0954 | 0.4065 |
| 9 | 33-36 | 2656 | 43.4081 | 12.3330 | 0.7846 | 0.0960 | 0.4089 |
| 10 | 37-40 | 2652 | 43.5107 | 12.3694 | 0.7787 | 0.0965 | 0.4102 |

Lower is better for MAE, pinball loss and Brier scores. Points are calculated with `score.py --points` after all submissions have been scored.
