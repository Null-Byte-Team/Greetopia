# ML pipeline (not trained yet)

No model or training dataset is bundled because no real, labeled sensor dataset was supplied. Do not invent metrics or claim a trained model exists.

Recommended next stage:
1. Export timestamped sensor readings and irrigation events from SQLite.
2. Define a target such as root-zone moisture stress within the next 30–60 minutes.
3. Split by time, not random rows, to avoid leakage.
4. Compare a simple baseline against a model and report precision/recall, calibration, and false watering triggers.
5. Keep model predictions as secondary evidence; the deterministic safety gate remains authoritative.
