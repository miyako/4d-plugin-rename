# Plugin release workflows

See [BUILD.md](BUILD.md) for the manual source-only **Bump version** and
separate zero-input **Build** workflow, version-authority evidence, preserved
Windows x64/macOS universal pipeline, required secret names, validation,
and create-only publication recovery.

Neither workflow runs on a tag push. Select a branch explicitly in Actions;
all jobs build its immutable selected `github.sha`.
