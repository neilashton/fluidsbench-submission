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
| `series-support-index.json` | `7df6ce95c5d6d4fef5ecd94e5d1dad0cda9ca2d491cd4223bbf6c55aacb6dbcc` |
| `releases/relative-diagnostics-v3-support-release-v1.json` | `db454016373221fcd14a87cb3f974ae955f0f13f12a1ec166716802105ccdd8a` |

Each manifest contains exactly the ordered 484 unique cases from
`proposal/native-source-pin.json` at public dataset revision
`7a5c0948ce27be709b1116a3a190f806e7a8f79f`. The index contains the 20
relative-family entries for every case: 16 relative velocity stations and four
relative Cp stations. It records only identities explicitly available from the
three producer releases. It does not reconstruct per-station constant-family
identities that those releases do not expose.

The release record binds the contract, profile schema, official case registry,
all three manifests, the series index, and evaluator Git revision
`a85b10f38cab4514b71ce6d64c73c001ba2407f9`. It records sensitivity evidence
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
