# Plugin release workflows

Two workflows, split so a version bump and an actual release are separate,
reviewable steps:

1. **`bump-version.yml`** — run manually (Actions tab → "Bump version" →
   Run workflow → choose patch/minor/major). Edits `MARKETING_VERSION` in
   `RENAME.xcodeproj/project.pbxproj`, commits, and pushes tag `vX.Y.Z`.
   It does not build anything.

2. **`release.yml`** — triggered automatically by that tag push (or push a
   tag yourself: `git tag v2.3.0 && git push origin v2.3.0`). Builds
   Windows x64 first (via MSBuild), then macOS as a universal
   arm64 + x86_64 binary (via xcodebuild, verified with `lipo`), merges the
   Windows `.4DX` into the macOS `.bundle`, codesigns + notarizes + staples,
   then publishes a GitHub Release with a `.zip` (cross-platform bundle,
   what most users download) and a `.dmg` (notarization ticket stapled, so
   Gatekeeper doesn't need to phone home).

Why split this way: pushing a tag from inside a workflow run also triggers
tag-push events, so if bump-version also built/released, you'd risk a
duplicate run. This way bump-version only ever produces a tag, and
release.yml only ever reacts to a tag — whoever created it.

## Per-project edits

At the top of `release.yml` and `bump-version.yml`:

```yaml
PRODUCT_NAME: RENAME          # matches PRODUCT_NAME / .xcodeproj target / .vcxproj name
XCODE_PROJECT: RENAME.xcodeproj
VCX_SOLUTION: RENAME.sln
```

These assume the same layout as your other plugins: `<Name>.sln`,
`<Name>.xcodeproj`, output bundle at
`test/Plugins/<Name>.bundle/Contents/{Windows,Windows64,MacOS,Resources}`.
That's exactly what this `rename` sample has, so it should drop in with
just the three values above changed per repo.

## Required repo secrets

| Secret | What it is |
|---|---|
| `APPLE_DEVELOPER_ID_CERTIFICATE` | Your Developer ID Application cert + private key, exported as `.p12`, then base64-encoded (`base64 -i cert.p12 \| pbcopy`) |
| `APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD` | Password you set when exporting the `.p12` |
| `KEYCHAIN_PASSWORD` | Any password — just protects the temporary CI keychain, doesn't need to match anything |
| `NOTARYTOOL_APPLE_ID` | Apple ID email used for notarization |
| `NOTARYTOOL_TEAM_ID` | Your Developer Team ID (e.g. `Y69CWUC25B`) |
| `NOTARYTOOL_PASSWORD` | An **app-specific password** for that Apple ID (generate at appleid.apple.com → Sign-In and Security → App-Specific Passwords), not your normal Apple ID password |

`GITHUB_TOKEN` (automatic, no setup) needs `contents: write`, which is
already set in both workflow files — used for pushing the version-bump
commit/tag and for creating the Release.

## Notes / things worth checking before first real run

- The Windows build overrides `PlatformToolset` to `v143` on the command
  line, since GitHub's `windows-latest` runner doesn't ship the legacy
  `v140` toolset your `.vcxproj` is pinned to. If you rely on
  something v140-specific, install the toolset via a `choco` step instead
  and drop the override.
- `MACOSX_DEPLOYMENT_TARGET` is passed on the xcodebuild command line to
  match what the project already declares (10.13) — bump this in one place
  if you raise your minimum macOS version.
- The `jsoncpp` static libs are already checked into the repo
  (`lib/windows`, `lib/windows64`, `a/libjsoncpp.a`), so no extra
  dependency install step is needed — this mirrors what your local builds
  already do.
- First run: do a `workflow_dispatch` on `release.yml` against a tag you've
  already pushed by hand, to shake out signing/notarization issues without
  needing to go through bump-version first.
