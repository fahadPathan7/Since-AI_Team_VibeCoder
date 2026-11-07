# Score summary

- Scorer version: 0.1.1
- Schema version: 1.0
- Submission: forecast_backtest.csv
- Actuals: actuals_validation.csv
- Spike margin: 50.00 EUR/MWh
- Rows in submission: 26880
- Rows scored (price metrics): 26700; skipped (no actual): 180
- Rows scored (exceptional prices): 26700
- Rows scored (direction): 26700

## Overall results

| Metric | Value | Use |
|---|---|---|
| MAE (p50) | 66.2033 | Level 1: accuracy |
| Pinball loss p10 | 25.1076 | |
| Pinball loss p90 | 23.2477 | |
| Mean pinball loss p10 and p90 | 24.1776 | Level 1: calibration |
| P10-P90 coverage | 0.6829 | supporting metric (target about 0.80) |
| Brier p_spike_high | 0.1083 | |
| Brier p_spike_low | 0.1181 | |
| Mean Brier, exceptional prices | 0.1132 | Level 1: exceptional prices |
| Three-class Brier, direction | 0.4509 | Level 1: direction |
| Pinball loss p50 | 33.1017 | for information |
| Observed share of high / low quarter-hours | 0.1213 / 0.1296 | for information |
| Baseline MAE (p50) | n/a | for information |
| MAE difference vs baseline (team - baseline) | n/a | for information |
| MAE ratio vs baseline (team / baseline) | n/a | for information |

## Results by forecast horizon

| Hour | Steps | Rows | MAE | Pinball p10/p90 mean | Coverage | Brier spikes | Brier direction |
|---|---|---|---|---|---|---|---|
| 1 | 1-4 | 2688 | 51.7431 | 19.8958 | 0.7035 | 0.1125 | 0.4513 |
| 2 | 5-8 | 2684 | 57.1259 | 21.1494 | 0.6841 | 0.1126 | 0.4516 |
| 3 | 9-12 | 2680 | 62.2554 | 22.7755 | 0.6851 | 0.1128 | 0.4514 |
| 4 | 13-16 | 2676 | 64.8414 | 23.6000 | 0.6831 | 0.1129 | 0.4509 |
| 5 | 17-20 | 2672 | 66.4223 | 24.0854 | 0.6868 | 0.1131 | 0.4503 |
| 6 | 21-24 | 2668 | 68.5002 | 25.0686 | 0.6942 | 0.1133 | 0.4501 |
| 7 | 25-28 | 2664 | 70.1561 | 25.5614 | 0.6944 | 0.1134 | 0.4504 |
| 8 | 29-32 | 2660 | 72.5799 | 26.4802 | 0.6733 | 0.1136 | 0.4507 |
| 9 | 33-36 | 2656 | 74.3465 | 26.7499 | 0.6668 | 0.1137 | 0.4510 |
| 10 | 37-40 | 2652 | 74.3573 | 26.5030 | 0.6572 | 0.1139 | 0.4513 |

Lower is better for MAE, pinball loss and Brier scores. Points are calculated with `score.py --points` after all submissions have been scored.
