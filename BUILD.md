# Plugin release workflows

## Manual source bump and manual Build

Run **Bump version** from Actions, explicitly selecting a branch and
`patch`, `minor`, or `major`. It validates the selected immutable commit and
coordinated source metadata, then pushes one direct-child source-only commit
to that branch. It never creates a tag, dispatches Build, or builds anything.
Both the initial remote read and Git's actual pre-push advertisement must
match the selected SHA. An advance, rewind, deletion, or already-up-to-date
same-result race fails; select the branch again in a new dispatch.

Run **Build** separately from Actions using the branch selector. It has
**zero inputs**, no push/tag/PR trigger, and checks out `github.sha` in every
job. No branch restriction was present in the original workflow.
The source version alone determines `vX.Y.Z`, `RENAME-X.Y.Z.zip`, and
`RENAME-X.Y.Z.dmg`. Build fails rather than repairing inconsistent metadata.
All branches share the constant `release-publication` concurrency group
with cancellation disabled.

At intake, Bump was already manual with one `mode` choice. Build & Release
ran on `v*.*.*` tag pushes or manual dispatch with one required `tag`
input. These original trigger definitions were read directly from the
committed workflows; the API default branch and symbolic remote HEAD both
resolve to `master`.

## Version authority and migration evidence

The intake authority is **2.2.5**, not a new increment. At
`1c91c2b9d986231277dcdbfe5d02405f42416de2`, all six
`MARKETING_VERSION` assignments and the source `Info.plist`
`CFBundleShortVersionString` already said 2.2.5. Six
`CURRENT_PROJECT_VERSION` assignments were stale at 2.2.3; copied source
`English.lproj/InfoPlist.strings` display/info versions were stale at 2.2.2.
This migration changes only those stale source values to 2.2.5.
The absent source `CFBundleVersion` remains absent.
The existing remote `v2.2.5` tag and published release are retained;
Build at the intake version must reject that collision. A maintainer's
first future publication requires a manual source bump, then manual Build.

History was followed across the workflow's rename:
`6d6bcac` introduced `.github/bump-version.yml` with the marketing-only
header "Bumps MARKETING_VERSION"; `4eca757` moved it unchanged to
`.github/workflows/bump-version.yml`. That original contract alone would
preserve an independent build number, even one equal to marketing.
However, `193f430cec6949ff7f44a7f3c8cecfc3456b76d9` explicitly superseded
it: the new header promises to write the same version into
**MARKETING_VERSION/CURRENT_PROJECT_VERSION AND
CFBundleShortVersionString/CFBundleVersion**. Its commit message also
promises coordinated consistency and adds the missing configuration keys.
The buggy body still chose marketing first and current only as fallback.
The explicit later header, not that buggy body or absence of independent
wording, governs this repository.

The Xcode resource phase copies `English.lproj/InfoPlist.strings`; its
`RENAME version X.Y.Z, Copyright 2021 miyako.` text is user-visible.
The helper validates all six settings, literal and supported
`$(MARKETING_VERSION)` / `${MARKETING_VERSION}` references, and supported
plist references to either coordinated key. Cyclic/unknown references,
malformed/duplicate metadata and drift fail before any file is written.
Optional absent keys stay absent. Literal versions change without
reserializing files: BOM, CR-only/CRLF/mixed endings, modes, whitespace,
copyright, and unrelated bytes are preserved.

Only these source paths can enter a generated bump commit:

- `RENAME.xcodeproj/project.pbxproj`
- `Info.plist`
- `English.lproj/InfoPlist.strings`

Committed bundles, zip/dmg files, dependencies, native source, Windows
projects, 4D data/schema, manifests and localization counters are excluded.
The generated commit includes the Copilot App co-author trailer. The
executable `.github/scripts/bump-hooks/pre-push` is mandatory initially and
immediately before push. It verifies one literal new HEAD, one direct
parent, exact old selected SHA, exact target, and exactly one update.
The non-force push sets both `push.followTags=false` and `--no-follow-tags`.

Exact committed prior art (full source/helpers/tests fetched for adaptation):

| Repository | Commit | Contract used |
|---|---|---|
| `miyako/4d-plugin-native-encoding-detection` | `c42ca565857f674bde5ea6ed3435c87375eda4a7` | Coordinated six configurations, strict strings tokenizer, fail-closed cleanup, advertised-SHA hook, create-only publication |
| `miyako/4d-plugin-file-information` | `19848973601acfd3a2b5070230fa40cdc7e4edb2` | Coordinated three configurations; UTF-16/binary built localization, explicit i386 rejection |
| `miyako/4d-plugin-common-string-algorithm` | `2606a68201866ec9fcbb38b51462d79215f504ef` | Independent build preservation, not applied as rename's authority |
| `miyako/4d-plugin-window-button` | `3f14facb9aaaaff0e22eeb8e07531163680c3a8a` | Corrected independent-build reference behavior; unsupported display-to-independent-build bumps reject before writes |

## Native pipeline preserved

Windows x64 still builds first on `windows-latest` with MSBuild,
Release/x64, `PlatformToolset=v143`, `WindowsTargetPlatformVersion=10.0`,
and the existing checked-in jsoncpp libraries. No Win32 job is invented:
the actual workflow removed Win32 in `093b556`; its old introductory
comments/documentation were not authority for adding a platform.
The `windows-binaries` artifact remains the single `.4DX`.

macOS still builds on `macos-latest`, target RENAME, configuration Default,
`ARCHS="arm64 x86_64"`, `ONLY_ACTIVE_ARCH=NO`,
deployment target 11.0, and `CODE_SIGNING_ALLOWED=NO`.
The original certificate import, keychain, notary profile, deep/runtime
codesigning and strict verification, ditto zip, UDBZ dmg, two notarization
submissions and DMG stapling remain. There is no toolchain modernization.

Narrow selected-source safety fixes address demonstrated stale outputs:
the old cleanup deleted committed Resources and QuickLook (and Windows32)
alongside the Mac product; the old recursive "first .4DX" search could
select committed output. Cleanup now invalidates only exact native outputs
and intermediates while preserving committed resources and other-platform
artifacts. Windows normalization uses the exact x64 output declared in
`RENAME.vcxproj`, and Mac merging uses the exact downloaded artifact.
Fresh built plist/localized metadata must match selected source before
signing. The universal gate requires arm64 and x86_64 and rejects i386
explicitly. Both notary responses must report **Accepted**, not merely
exit zero, before stapling/publication.

## Create-only publication and recovery

Before native work, and again after all build/sign/notary/staple gates,
the helper checks the exact remote tag and authenticated, fully validated
paginated releases, including drafts. A tag, draft, or published release
collision fails even at the same SHA. Authentication failures, 404,
network errors, malformed data and errors on later pages all fail closed.

Publication performs exactly these new-object operations:

1. POST `git/refs` for `refs/tags/vX.Y.Z` at the selected SHA, then verify
   the exact remote tag SHA.
2. POST a new public, non-prerelease release with explicit tag, selected
   target SHA, original tag-name title and original empty body (no generated
   notes).
3. POST the two exact versioned assets to the newly returned release ID.

There is no tag/release reuse, update, delete, clobber, rollback or retry,
and no `gh release create` implicit tag creation.
**Partial state is retained on every error**, including ambiguous network
responses. Inspect the remote tag, release/draft and uploaded asset list,
and record the failed run and selected SHA before deciding recovery.
Do not rerun this version expecting repair: the availability checks reject
it. A maintainer must assess retained state manually, or source-bump to a
fresh version and run Build on that selected branch. The automation never
deletes or rolls back published state.

## Required repository secret names

| Secret | Purpose |
|---|---|
| `APPLE_DEVELOPER_ID_CERTIFICATE` | Base64 Developer ID Application certificate/private key `.p12` |
| `APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD` | Password for the `.p12` |
| `KEYCHAIN_PASSWORD` | Temporary CI keychain password |
| `NOTARYTOOL_APPLE_ID` | Notarization Apple ID |
| `NOTARYTOOL_TEAM_ID` | Notarization team ID |
| `NOTARYTOOL_PASSWORD` | Apple app-specific password |

`GITHUB_TOKEN` supplies `contents: write` for the one branch update or
new tag/release/assets. No secret values belong in this repository.

## Non-native validation

```sh
actionlint
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s .github/tests -v
```

The suites use disposable source copies, real local bare Git remotes,
mocked GitHub APIs and closed-PATH native command stubs, including
PowerShell when available. Run them on both the live tree and a disposable
copy after a source bump. These checks do not execute real native builds,
signing, notarization, 4D, workflow dispatches or production publication.
