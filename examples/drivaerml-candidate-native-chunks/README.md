# DrivAerML native-chunk reference drivers

These examples cover two different purposes. Neither activates the DrivAerML
contract or represents owner approval.

## One-command synthetic package

`reference_driver.py` is a tiny teaching fixture. It uses no VTP, VTU,
DrivAerML truth, real model, fixed area array, or real volume weight. After
installing the candidate requirements, one driver command creates and
schema-validates a complete dummy schema-v3 package, including
`submission.json`:

```bash
python3 -m venv .venv-drivaerml
.venv-drivaerml/bin/pip install -r requirements-drivaerml-evaluator.txt
.venv-drivaerml/bin/python examples/drivaerml-candidate-native-chunks/reference_driver.py \
  --output /tmp/drivaerml-synthetic-native-chunk-demo
```

The generated submission is explicitly synthetic and ineligible. It has no
approval block and belongs to the separate `synthetic-drivaerml-shaped`
namespace. Schema v3 requires the literal `scoring_support.status` value
`official`; the submission note limits that marker to the isolated fictional
support namespace. The bundled support manifest remains `prototype`, and the
driver requires the real `drivaerml` specification to remain exactly
`candidate_scoring_contract` / `owner_review_required` /
`submissions_open: false` before it runs. All generated package identifiers
must begin with `synthetic-` and differ from the real dataset ID.

The fixture demonstrates ordered two-part and three-part byte transport,
raw-cell IDs, independently bounded inference chunks, complete duplicate-free
coverage, additive sufficient statistics, full-case/chunked invariance, keyed
prediction packaging, case metrics, profile packaging, discretization records,
evaluation evidence, and local validation against every applicable repository
JSON Schema. Its transport bytes are JSON, not VTK.

The driver performs those schema checks as part of the one command. The
fictional dataset ID is deliberately not registered with the normal
`scripts/validate_submission.py` official-dataset validator, so that validator
will reject this teaching package. This keeps the real closed DrivAerML
contract fail-closed rather than creating a synthetic acceptance path.

## Real run_1/run_44 pilot

`real_reference_driver.py` is a small fail-closed orchestrator for exactly:

- `run_1`, whose pinned logical VTU has two byte parts; and
- `run_44`, whose pinned logical VTU has three byte parts.

It imports and calls the repository's core and AutoCFD5 candidate evaluator
entry points. Scientific reductions are not copied into the example. Both
cases always use the verified ordered multipart stream. The driver consumes
the immutable source pin, Neil's fixed surface-area arrays, source-bound volume
weights plus every receipt in their aggregate, participant prediction chunks,
Cp support, and the 10 mm velocity mapping/receipt. It downloads and generates
nothing.

The orchestrator interface is implemented, but the real pilot is currently
blocked: no valid source-bound physical-volume weights or pilot aggregate exist
because the candidate volume algorithm has not passed the strict positive and
finite gate. Do not create substitute participant weights. Once the owner
publishes an accepted pilot, copy `real-case-inputs.example.json`, replace its
paths, and run as follows (repeat `--volume-weight-receipt` for every receipt
listed by the supplied aggregate):

```bash
python3 -m venv .venv-drivaerml
.venv-drivaerml/bin/pip install -r requirements-drivaerml-evaluator.txt
.venv-drivaerml/bin/python examples/drivaerml-candidate-native-chunks/real_reference_driver.py \
  --case-inputs /path/to/real-case-inputs.json \
  --native-source-pin benchmark-specs/drivaerml/proposal/native-source-pin.json \
  --dataset-root /path/to/pinned/drivaerml \
  --volume-weight-aggregate /path/to/pilot-volume-weight-aggregate.json \
  --volume-weight-receipt /path/to/run_1-volume-weight-receipt.json \
  --volume-weight-receipt /path/to/run_44-volume-weight-receipt.json \
  --allow-incomplete-volume-weight-pilot \
  --pilot-volume-weight-aggregate-sha256 LOWERCASE_SHA256 \
  --output /path/to/new/run1-run44-evidence
```

The pilot flags are mandatory while the all-484 volume-weight aggregate hash
is not frozen in the evaluator. Removing them does not bypass the gate:
production evaluation fails closed. Successful pilot output contains core and
diagnostic candidate evidence for both cases plus a hashed validation receipt;
it never contains `submission.json`.

Prediction `.npz` files remain bounded inputs: the loader caps an NPY header at
4 KiB, total uncompressed archive content at 512 MiB, and the ZIP central
directory at 64 KiB. Split transport parts and inference chunks are independent
concepts. Never average chunk-local RMSE values; let the evaluator accumulate
additive statistics and reduce once after complete raw-cell coverage.
