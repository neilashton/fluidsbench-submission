# DrivAerML relative-v3 support release

This directory retains the exact producer manifests used by the inactive
DrivAerML relative-diagnostics candidate. Ordinary submission validation reads
only these repository files; it performs no network access and does not depend
on the producer workspace.

| Artifact | SHA-256 |
| --- | --- |
| `manifests/velocity-placement-all484-v1.json` | `70627d6af9e6b254739b29d54d856b470d6152066e09a1097ebe20c034179925` |
| `manifests/velocity-mapping-all484-v1.json` | `9b88c36e2268bf72c9baec9418ef2d9afc9faba1d98c9c12ed73b79e683a6a3d` |
| `manifests/cp-native-support-all484-v3.json` | `4e6a4c3495ea4938895868162480dcb20b5bbea42114c94013a2c76e26128c90` |
| `series-support-index.json` | `ff7b8bdb0b963611ce7ecb2055090b6861d42477ff47976d7b164ff131d82632` |
| `run419-constant-series-support-index.json` | `c66adf17b73fbe0c4cba080e2ee44e2046f7c69cc7e5a5e797b2b973c826b211` |
| `releases/relative-diagnostics-v3-support-release-v1.json` | `ec853a95ec113a1387c0cadad384c0feac39b5f9a92a5c3c43ed75d6c7f9a151` |

Each manifest contains exactly the ordered 484 unique cases from
`proposal/native-source-pin.json` at public dataset revision
`7a5c0948ce27be709b1116a3a190f806e7a8f79f`. The index contains the 20
relative-family entries for every case: 16 relative velocity stations and four
relative Cp stations. For each materialized relative series it retains the
producer-derived coordinate count and coordinate identity; shared centreline
aliases intentionally omit both and continue to reference their canonical
constant supports. It records only identities replayed from the three producer
releases. It does not reconstruct per-station constant-family identities that
those releases do not expose.

## Canonical coordinate-array identity

`reference/drivaerml/coordinate_identity.py` defines the platform-independent
encoding used by the index and submission validator. The byte stream is the
NUL-terminated ASCII domain
`fluidsbench-drivaerml-coordinate-array-v1`, followed by an unsigned 64-bit
big-endian element count, followed by each coordinate as an IEEE-754 binary64
in big-endian byte order. Non-finite values and booleans are rejected, and both
signs of zero are encoded as positive zero. The retained identity is the
lowercase SHA-256 of that complete stream.

For relative velocity, the generator verifies the exact 10 mm mapping artifact
against its retained all-484 aggregate digest, joins every ordered mapping row
to the exact placement CSV point and distance, and hashes the placement CSV's
`line_fraction` values for rows whose native-cell assignment is valid. Thus an
explicit invalid native-cell row is omitted rather than assigned an invented
prediction. For materialized relative Cp cuts, it hashes the producer support's
ordered `rows[].interval_arc_end_m` values. This preserves declared local arc
resets between sidewall intervals; the exact producer order is protected by the
identity rather than rewritten into a different coordinate convention.

## Real run_419 constant-series fixture binding

`run419-constant-series-support-index.json` binds the 20 materialized constant
series used by the real Transolver regression fixture: 16 constant velocity
profiles and four constant Cp cuts. Each entry records the verified producer
support identity, placement-receipt identity, coordinate count, and canonical
coordinate-array identity. The constant velocity producer maps 3,684 of its
3,756 frozen-grid rows and explicitly marks 72 as unsupported. The fixture
therefore emits only ordered valid points and may preserve interior gaps. Such
sparse arrays are accepted only for `run_419` when all four retained bindings
match; they are report-only regression evidence and do not activate or alter
constant-family scoring support. Other cases must provide the complete frozen
constant velocity grid.

The release record binds the contract, profile schema, official case registry,
all three manifests, the series index, and evaluator Git revision
`b9db402a3fa0efbb94fe36be2ba1fe6f7b4bc1e1`. It records sensitivity evidence
and owner approval as pending. Consequently it has
`profile_format_authorized=false`, keeps the relative composite weight at
`0.0`, and does not open submissions. Publishing and verifying support bytes is
not scientific activation.

The source outputs were found in the completed local relative-diagnostics
producer workspace. Its enclosing PhysicsNeMo checkout had base revision
`651c62656dd4f0ce5de9cd5afd0dbc389ae105bc`, but it also contained tracked and
untracked producer work. Therefore that revision is context, not a claim that
the whole producer tree was clean; the retained bytes and SHA-256 values above
are the release authority.

Maintainers with the producer workspace can replay the index with:

```bash
python scripts/generate_drivaerml_relative_support_index.py \
  --producer-root /path/to/drivaerml_relative_diagnostics_candidate_v1_20260824 \
  --check
```

The compact run_419 constant binding can be replayed independently from its
actual producer artifacts with:

```bash
python scripts/generate_drivaerml_run419_constant_support_index.py \
  --constant-velocity-case-dir /path/to/velocity/receipts/run_419 \
  --constant-cp-campaign-root /path/to/production_path_all484_v8 \
  --check
```
