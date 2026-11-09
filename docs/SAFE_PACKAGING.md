# What goes into a skill package

Both packaging commands validate a private copy and apply any repairs there. The archive is created as a new file. An existing archive or symlink at the destination blocks creation. [Packaging workflow](USER_GUIDE.md#package-and-share) · [Packager source](../skills/skill-creator/scripts/package_skill.py)

The packager skips known sensitive filenames such as `.env`, private keys, and credential files. It normalizes names before checking for lookalikes such as `.env ` or `notes.pem.`. The archive also excludes designated local state, caches, and generated directories such as `evals/`, `runs/`, and `dist/`. Snapshot checks reject links, junctions, and other special files in the files selected for copying and enforce size limits. [File policy](../skills/skill-creator/scripts/file_policy.py)

To choose exact files, add a `package-manifest.json` to the skill folder. For example:

```json
{"files": ["SKILL.md", "references/guide.md"]}
```

The manifest must include `SKILL.md` and can list only existing, permitted files. The archive retains the manifest and any existing review record. Filename checks cannot detect a token pasted into `guide.md` or private details written into a review. Inspect the archive contents before sharing. [Packaging permissions](../skills/skill-creator/PERMISSIONS.md#enforced-core-boundaries)
