# What goes into a skill package

Both packaging commands validate a private copy and apply any repairs there. The archive is created as a new file. An existing archive or symlink at the destination blocks creation. [Packaging workflow](USER_GUIDE.md#package-and-share) · [Packager source](../skills/skill-creator/scripts/package_skill.py)

The packager skips known sensitive filenames such as `.env`, private keys, and credential files. It normalizes names before checking for lookalikes such as `.env ` or `notes.pem.`. The archive also excludes designated local state, caches, and generated directories such as `evals/`, `runs/`, and `dist/`. Snapshot checks reject links, junctions, and other special files in the files selected for copying and enforce size limits. [File policy](../skills/skill-creator/scripts/file_policy.py)

A file that `SKILL.md` or `skill.yaml` names is not silently dropped. When its folded name matches that secret-file list, `check` and `package` both fail and name the pattern. For `references/secrets.md` the message says the file is excluded because the name matches `secrets.*`, and that it has to be renamed to ship. The same applies to other secret-like names, such as `credentials` or a `*.key` sample. The package report lists every path the policy skipped, including unreferenced secret-like names and excluded directories.

To choose exact files, add a `package-manifest.json` to the skill folder. For example:

```json
{"files": ["SKILL.md", "references/guide.md"]}
```

The manifest must include `SKILL.md` and can list only existing, permitted files. The archive retains the manifest and any existing review record. Filename checks cannot detect a token pasted into `guide.md` or private details written into a review. Inspect the archive contents before sharing. [Packaging permissions](../skills/skill-creator/PERMISSIONS.md#enforced-core-boundaries)

## Reference containment and credential warnings

The analyzer checks literal and defensively normalized paths for containment before
packaging. Checks cover nested percent encoding, Unicode separator lookalikes,
compatibility characters, backslashes, and invisible marks. File access and archive
entries retain the literal spelling, including legitimate Unicode and percent signs.

Credential-content scanning uses a bounded source snapshot that rejects links.
Warnings identify the file, line, and pattern category without printing the matched
value. They are advisory. The existing secret-filename exclusions still apply.
