"""Illustrative reliability arithmetic; not a robot simulation or performance test."""
import json
import math
from pathlib import Path

root = Path(__file__).resolve().parents[1]
rows = []
for p in [0.90, 0.95, 0.98, 0.99, 0.995, 0.999]:
    q = p * p
    rows.append({
        "per_direction_success_probability": p,
        "cycle_success_probability": q,
        "probability_of_20_uninterrupted_cycles": q ** 20,
        "expected_complete_cycles_before_first_failure": q / (1 - q),
    })
result = {
    "scope": "Hypothetical fixed-policy IID arithmetic. Every task failure requires human help; no automatic retry/recovery. Not a prediction for any paper or robot.",
    "rows": rows,
    "equal_per_direction_p_for_90pct_survival_over_20_cycles": 0.9 ** (1 / 40),
    "one_sided_exact_95pct_lower_bound_after_20_of_20_successes": 0.05 ** (1 / 20),
    "zero_failure_trials_for_one_sided_95pct_lower_bound_at_least_99pct": math.ceil(math.log(0.05) / math.log(0.99)),
    "caveats": [
        "Real cyclic robot trials are correlated and may drift; estimate actual intervention-free run survival from logs.",
        "With autonomous recovery, task failure is not the same event as manual intervention.",
        "The zero-failure confidence formula assumes independent, identically distributed fixed-policy trials.",
    ],
}
out = root / "evidence" / "cycle_reliability_examples.json"
out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
