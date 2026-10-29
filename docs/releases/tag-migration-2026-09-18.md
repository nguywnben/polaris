# Historical tags separated from Polaris

Completed on 2026-09-18 under the owner's explicit authorization. This metadata-only
migration frees the Polaris version names without discarding Omni Gateway history.
It does not publish the uncommitted Polaris 1.0.0 candidate or change Docker images.

## Verified mapping

The same mapping is present locally and on `nguywnben/polaris`. Each archive ref
retains the original Git object, including its annotation; its internal annotation
may therefore still contain the old tag name. No commit was rewritten.

| Former tag | Current tag | Commit prefix |
| --- | --- | --- |
| `v0.1.0-beta` (Omni Gateway) | `omni-gateway/v0.1.0-beta` | `ca5a016fd346` |
| `v0.2.0-beta` | `omni-gateway/v0.2.0-beta` | `9e858310c956` |
| `v1.0.0` | `omni-gateway/v1.0.0` | `36ef7651ef9b` |
| `v1.1.0` | `omni-gateway/v1.1.0` | `6b78418f8e9e` |
| `v1.1.1` | `omni-gateway/v1.1.1` | `4d9f095b96bf` |
| `v1.1.2` | `omni-gateway/v1.1.2` | `e5976f20a6fc` |
| `v1.1.3` | `omni-gateway/v1.1.3` | `704df582b692` |
| `v1.1.4` | `omni-gateway/v1.1.4` | `4765bbdce6c8` |
| `v1.2.0` | `omni-gateway/v1.2.0` | `07e2c54e0e3c` |
| `v1.2.1` | `omni-gateway/v1.2.1` | `de9f278505a0` |
| `v1.3.0` | `omni-gateway/v1.3.0` | `e91fc0e1f8c1` |
| `v1.3.1` | `omni-gateway/v1.3.1` | `a1e02f131cc8` |
| `v1.3.2` | `omni-gateway/v1.3.2` | `890b42b74494` |
| `v1.4.0` | `omni-gateway/v1.4.0` | `545092609389` |
| `v0.1.0-beta.1` (Polaris) | `v0.1.0-beta` | `30e50ea78b57` |

The [Polaris prerelease](https://github.com/nguywnben/polaris/releases/tag/v0.1.0-beta)
retains release ID `388233610`, commit
`30e50ea78b57b80559a453e6cdd6ea31b3b30710`, and the prerelease flag. Its title is
`Polaris 0.1.0-beta`. Its new annotated tag preserves the original tagger date.
The old `v0.1.0-beta.1` ref and the unprefixed Omni Gateway refs were removed only
after replacement refs and releases were verified. `v1.0.0` is currently absent.

All 15 release IDs, notes, publication dates, creation dates, draft/prerelease flags
and asset lists were compared before/after and preserved. None had attached assets.
The CI and Docker publication workflows were temporarily disabled and restored to
their original active state; no branch or container image was pushed.

An initial verification stopped before old-name deletion because creating the renamed
beta tag with a new tagger timestamp changed GitHub's `created_at`. The timestamp was
restored from the original tag, then the complete strict comparison passed. The
original publication date remains 2026-09-14; this was not a new beta release.

## Existing clones and links

An existing clone may still resolve `v0.1.0-beta` to Omni Gateway. Normal fetching does
not automatically replace a conflicting local tag. After checking that no private
local tag needs preserving, fetch the archive namespace and explicitly refresh only
the renamed Polaris beta:

```sh
git fetch origin 'refs/tags/omni-gateway/*:refs/tags/omni-gateway/*'
git fetch origin '+refs/tags/v0.1.0-beta:refs/tags/v0.1.0-beta'
git rev-parse 'refs/tags/v0.1.0-beta^{commit}'
```

The last command must print `30e50ea78b57b80559a453e6cdd6ea31b3b30710`.
Update automation and release links to the mapping above; do not rely on redirects
from old release URLs. Historical source contents and already-published image labels
are unchanged, so they may still report the former version string.

## Recovery and remaining publication work

The operator's local recovery directory is
`temp/tag-migration-20260918T053010Z/`. It contains a verified `before.bundle`,
`before.json` with original object/commit IDs and complete release/workflow metadata,
`after.json` with final verified state, and workflow-restoration records. These ignored
artifacts remain on the operator machine; they are not committed or uploaded.

To recover, first verify the bundle with `git bundle verify`, inspect `before.json`,
and restore only explicitly approved refs/releases after checking their current values.
Do not blindly restore all original tags: `v0.1.0-beta` now belongs to Polaris.
The archived remote refs independently preserve all 14 legacy Git histories.

GitHub tags and registry tags are separate. No Docker Hub/GHCR tag or image digest
was modified or certified by this operation. Follow the remaining
[1.0.0 publication checklist](1.0.0-preparation.md) before publishing that release.
