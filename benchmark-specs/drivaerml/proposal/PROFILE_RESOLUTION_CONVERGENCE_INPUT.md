# DrivAerML profile-resolution convergence input

This is a candidate evidence format. It does not activate scoring or open
submissions.

Run the checker with:

```bash
.venv/bin/python scripts/check_drivaerml_profile_resolution_convergence.py \
  --input study.json \
  --output evidence.json
```

The input uses schema
`drivaerml-profile-resolution-convergence-input-v1`. Its `losses` array is
indexed as `[method][case][profile][spacing]`; the declared orders must match
those dimensions exactly. `profile_order` is exactly `V1`-`V6`, `U1`-`U6`,
`L1`, `R1`-`R3`, and `spacings_mm` is exactly `[1, 2, 5, 10]`.

`method_set.methods` declares an ordered physics null, nearest-training-design
control, and genuine trained model/checkpoint methods. Each declaration pins
its prediction artifact by SHA-256, and the canonical JSON hash of the whole
ordered method array is supplied as `method_set.sha256`. At least three
distinct trained model/checkpoint pairs with distinct prediction-artifact
hashes are required for eligibility. The checker validates those declarations
structurally; scientific authenticity and approval still require owner review.

The checker writes complete aggregate, case-macro, and case-line comparisons
for 2, 5, and 10 mm against 1 mm, plus Kendall tau-b method-order evidence. It
returns exit code 0 for an eligible candidate study, 1 for valid but ineligible
evidence, and 2 for malformed or contract-drifted input. Even an exit-code-0
result explicitly remains non-activating pending owner approval.

Minimal top-level shape:

```json
{
  "schema": "drivaerml-profile-resolution-convergence-input-v1",
  "schema_version": 1,
  "study_id": "immutable-study-id",
  "method_set": {
    "pinned_before_study": true,
    "sha256": "<canonical ordered methods SHA-256>",
    "methods": ["<method objects>"]
  },
  "case_order": ["run_1", "run_44"],
  "profile_order": ["V1", "V2", "V3", "V4", "V5", "V6", "U1", "U2", "U3", "U4", "U5", "U6", "L1", "R1", "R2", "R3"],
  "spacings_mm": [1, 2, 5, 10],
  "losses": ["<method x case x profile x spacing finite nonnegative losses>"]
}
```

Use `reference.drivaerml.profile_convergence.method_set_sha256(methods)` to
derive the method-set pin; do not hand-edit it after losses have been produced.
