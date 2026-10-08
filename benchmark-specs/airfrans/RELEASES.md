# AirfRANS development intake

**Intake is open on `dev` for Full, Scarce and AoA extrapolation.** Submit a new
schema-v3 result directory through a PR against **`dev`**. Reynolds extrapolation
is closed: 318 of its 496 evaluation cases are not covered by these supports.
Other datasets and production intake remain closed.

Full and Scarce share the ordered 200-case evaluation set; AoA uses 196 cases.
The approved native support and lossless profile truth cover 355 unique cases.
The score contract was approved by Neil Ashton in [PR #47](https://github.com/neilashton/fluidsbench-submission/pull/47).
No participant result is approved or ranked by opening intake. Existing
prototype fixtures and candidate references keep their original bytes and
historical identities in the unranked development feed.

## Editable dev downloads

- [Native support](https://github.com/neilashton/fluidsbench-submission/releases/tag/airfrans-native-support-v1)
- [Lossless profile truth](https://github.com/neilashton/fluidsbench-submission/releases/tag/airfrans-native-profile-truth-v1)

These are editable GitHub **prereleases**, tied to the approved `dev` source
commit. Release locking is disabled. Bug fixes remain possible; changed files
must have matching new hashes in the dev contract before they are accepted.
Neither submission `main` nor the production website is changed.

The archives and approval records retain the original preparation snapshot:
`prepared_dev_only`, with formal publication and intake recorded as closed at
preparation time. The **current** intake state comes from the canonical
[`submission-spec.json`](submission-spec.json) on `dev`, which selects that
approved contract and opens only its three supported splits. The separately
stored [approval binding](official-release-binding.json) preserves the reviewed
artifact hashes; it is not the current intake switch.

## Install and verify

Use a source checkout of `dev` and install `requirements.txt`. Keep the two
downloads in separate directories because they contain files with the same names.
For example, with GitHub CLI:

```bash
mkdir support-download truth-download
gh release download airfrans-native-support-v1 --repo neilashton/fluidsbench-submission --dir support-download
gh release download airfrans-native-profile-truth-v1 --repo neilashton/fluidsbench-submission --dir truth-download
```

In each download directory, run `shasum -a 256 -c SHA256SUMS` (macOS) or
`sha256sum -c SHA256SUMS` (Linux) before extracting. The support download includes
its JSON schemas. Extract `support-metadata.tar.gz` and `native-tables.tar` into
the **same empty directory**. It will contain `manifest.json`, `case-sets/` and
`tables/`. Archive descriptors bind both the archive and each installed member.
The evaluator reads verified local members and does not fetch files itself.

```bash
python scripts/publish_airfrans_official_release.py --verify-native /path/to/installed/support
```

Extract `profile-truth.tar.gz` into a **different empty directory**, then run:

```bash
python scripts/validate_airfrans_profile_truth.py --release /path/to/installed/profile-truth
```

Native verification loads 1,188 support instances across two ordered case sets
(396 case references, 355 unique cases). Profile verification checks all 355
lossless case arrays and their source-mesh, extractor, runtime and hash bindings.
CI checks committed metadata and the complete artifact-validation receipt.

## Evaluate and submit on dev

Use `airfrans-native-v1` as the dataset version and `airfrans-scoring-v2` as the
evaluator version. Select the exact split ID from the canonical specification:
`full`, `scarce`, or `aoa_extrapolation`. Bind `scoring_support` to
`airfrans-native-support-v1`, its declared manifest URL and SHA-256, with
`status: official`. Bind profile data to the **dataset-local**
`airfrans-native-profile-truth-v1` manifest and its declared SHA-256. The global
prototype leaderboard's truth binding is for historical examples.

Evaluate complete native coverage with the [reference evaluator](../../reference/README.md),
extract the required predicted profiles using the [AirfRANS extraction example](../../examples/airfrans-profile-extraction/README.md),
and finalize the profile and overall metrics with `scripts/finalize_airfrans_metrics.py`.
Prepare the [schema-v3 package](../../docs/RESULT_FORMAT.md) with its methodology,
checkpoint digests, compute, discretization, case metrics and evaluation evidence.
The older `*-candidate` assembly and rescoring scripts are for historical
candidate workflows; they do not create an approved intake result.

```bash
python scripts/validate_submission.py --contributor-stage submissions/airfrans/<new-submission-id>
```

Open a PR against `dev` containing exactly that new directory. Do not add
approval metadata. Maintainers review the package and create approval in a
separate PR; the approval workflow dispatched on `dev` targets `dev`.
Passing contributor validation does not publish or rank a result. Code, model
weights and complete prediction-field sharing remain optional.

## Approved scoring contract

Dataset version: `airfrans-native-v1`. Evaluator version: `airfrans-scoring-v2`;
the scientific implementation is pinned to
`b320575e35d6f61f94ac852fdb084dec080e4ecb`. Native table bytes and profile payloads
are identical to the verified handover; publication changed only independently
bound release metadata. No model inference or source-data re-extraction was run.

The score weights are unchanged: curve pressure 15%, curve wall shear 10%,
domain velocity 15%, domain pressure 10%, drag R2 15%, lift R2 10%, and boundary
layer profile R2 25%. Field caps remain 15, 20, 12, and 15 respectively. Curve
primary errors use native dual lengths; domain primary errors use equal native
nodes. Alternate equal-entity/physical-weight errors remain diagnostics. The
four profile stations, two Cartesian quantities, and 1,001 samples per series
remain bound to `airfrans-boundary-layer-v1`.
