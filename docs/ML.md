# ML stress predictor (experimental)

**Task:** probability that root-zone moisture falls below the plant's profile minimum within the next `horizon` minutes (default 60). **It never publishes commands**; the decision engine may use an *approved* model only as corroborating evidence.

- **Labels** (`app/ml/dataset.py`): 10-minute bins (>= 20 samples each); y = 1 if any of the next `horizon/10` bins is below the minimum (strictly future); incomplete windows are dropped; rows with a confirmed watering inside the horizon are excluded so the model learns natural dry-down, not controller actions.
- **Features** (v1): root/mid/surface, temp, humidity, VPD, root slopes (30/60 min), depth differences, minutes since last watering, hour sin/cos. Each feature uses only data at or before t (a test proves truncating or tampering with the future does not change them).
- **Split:** chronological 60/20/20 with a purge gap equal to the horizon; time-series CV (gap = horizon) on train+val; models: logistic regression and gradient boosting; **baseline:** persistence rule on current root moisture.
- **Metrics:** precision, recall, F1, ROC-AUC, Brier, calibration bins, on validation and a held-out test period; stored with dataset SHA-256, feature schema, split dates, limitations.
- **Minimums:** >= 500 labelled rows, >= 30 stress rows in train+val, >= 10 in the test period, both classes in each split; otherwise `InsufficientData` and the predictor stays *unavailable*.
- **Registry** (`storage/models/<version>/`): models start `experimental`. `python -m app.ml.cli approve <version> --by you` refuses unless the model beats the baseline on the test period (ROC-AUC and F1). Only approved models whose SHA-256 matches are ever unpickled.
- **Not implemented:** online learning, per-plant personalisation, probability recalibration. Metrics from the synthetic data in the tests mean nothing about real plants.

```
python -m app.ml.cli train --plants plant01 plant02 --horizon 60
python -m app.ml.cli list
python -m app.ml.cli approve <version> --by you@example.com
```
