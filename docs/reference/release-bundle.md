# Release bundle

`swissknifeman release bundle` writes the files that accompany a release
([ADR 0077](../architecture/decisions/0077-release-bundle.md)). It is the `bundle` route of the `release` alias and
runs `aicore release bundle`; any other `release` word stays with `skiller release`.

```bash
swissknifeman release bundle --root . --tag v1.2.0 --out /tmp/skm-release
(cd /tmp/skm-release && sha256sum -c SHA256SUMS)
```

| Option | Meaning |
| --- | --- |
| `--root` | the hub root, a git repository |
| `--tag` | a label for names and `compat.json`; `[A-Za-z0-9][A-Za-z0-9._+-]*` |
| `--out` | a directory that is absent or empty (`OUT_NOT_EMPTY`, exit 2 otherwise); nothing is written elsewhere |

## Files

| File | Content |
| --- | --- |
| `compat.json` | `compat-manifest/v1`: the umbrella version and tag, and for every module and bridge its version, stability, destination, `requires` and contracts with their paths |
| `schemas-<tag>.tar.gz` | every file under `schemas/` of the modules, deterministic (sorted, fixed times, mode 0644), with `index.json` first |
| `release-attestation.json` | `release-attestation/v1` from `aicore.release.attestation`, taken at `HEAD` |
| `SHA256SUMS` | the checksums of the three files above, in `sha256sum` format |

## Notes

- Run the bundle on a committed tree. `compat.json` and the schema package come from the worktree, the attestation from
  `HEAD`, so a dirty tree makes them describe different states.
- The attestation names the tag of the top `CHANGELOG` version; `--tag` is only the label of the other files.
- SBOM, signatures and SLSA provenance are not part of the bundle; they wait for the publication trigger
  ([ADR 0023](../architecture/decisions/0023-releases-and-supply-chain.md)).
