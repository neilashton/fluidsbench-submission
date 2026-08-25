# DrivAerNet++ sample geometry

One real released surface file, included so the DrivAerNet++ publisher and profile-extraction
rules can be validated against genuine geometry without a full Dataverse/Globus download.

## Licence and attribution — read before reuse

| Item | Value |
|---|---|
| File | `DrivAer_E_S_WW_WM_075.vtk` |
| Source release | Harvard Dataverse `doi:10.7910/DVN/K7PWNJ` version 1.0 |
| SHA-256 | `2fca6566b41ae63cc8d4450f728629f3f8cf6b521038bd50ccf12bd2f6c57e58` |
| Size | 26,013,034 bytes (legacy VTK BINARY PolyData) |
| **Licence** | **CC BY-NC 4.0 — non-commercial use only** |
| Attribution | Elrefaie et al., *DrivAerNet++: A Large-Scale Multimodal Car Dataset with Computational Fluid Dynamics Simulations and Deep Learning Benchmarks* — https://arxiv.org/abs/2406.09624 |

> **This file does not carry the repository's Apache-2.0 terms.** It remains CC BY-NC 4.0 and
> is included here with the express permission of the dataset author (Mohamed Elrefaie) for
> benchmark-definition validation. Commercial use — including training models for commercial
> tools — is not permitted. Anyone redistributing or building on this file must observe the
> upstream licence, not the repository licence.

## Contents

| File | Purpose |
|---|---|
| `DrivAer_E_S_WW_WM_075.vtk` | Estateback, smooth underbody, WW wheels. 481,363 points / 442,114 cells; single PointData array `p` (kinematic gauge pressure, m²/s²). |
| `sample_split.json` | One-case split index so the publisher can be run directly on this file. |

## Reproducing the validation

```bash
python benchmark-specs/drivaernetplusplus/tools/publish_scoring_support.py \
  --vtk-dir benchmark-specs/drivaernetplusplus/samples \
  --split benchmark-specs/drivaernetplusplus/samples/sample_split.json \
  --out /tmp/dnpp-sample-release
```

Expected output:

```
materialized E_S_WW_WM_075: 481363 points
SELF-CHECK PASS: 1 case(s), identity/perturbation/chunk checks green
```

Reading the file requires a binary-capable VTK reader (`pip install pyvista`); the publisher
falls back to it automatically for BINARY payloads.

The measurements derived from this file — pressure convention, axis orientation, winding
inconsistency, connected-component structure, and dual-area weight statistics — are recorded
in [`../REAL_DATA_VALIDATION.md`](../REAL_DATA_VALIDATION.md).

## Scope

This is a **single geometry for validation only**. The full 1,154-case evaluation split is not
and will not be committed: it is roughly 12.5 GB once materialized, and the benchmark pins the
public release by DOI and checksum precisely so bulk data stays out of version control.
