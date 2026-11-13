# Security boundaries and offline coverage

Referenced paths are checked in their literal spelling and a defensive view that
repeatedly percent-decodes, folds compatibility characters, removes invisible marks,
and recognizes Unicode and Windows separator shapes. Backticked extensionless paths,
including directory forms, reach containment before runtime-output exceptions.
Normalization is only a rejection check: legitimate Unicode and literal-percent
filenames are read and packaged with their original spelling. Percentage prose is
not a file reference.

Credential-content scanning uses the same bounded, link-free source snapshot as
packaging. It emits advisory warnings with file and line locations and a credential
category, without matched values or source excerpts. Heuristic warnings can have
false positives and negatives; they do not prove a file is safe to distribute.
Secret-filename exclusions remain blocking when referenced and excluded from packages.

Claude subprocesses run with the caller's OS-account privileges. Tool allowlists,
hook disabling, source containment, and call budgets do not create an OS sandbox.
Use a restricted account or isolated environment when processing untrusted content.

The ten adversarial negative-trigger cases in tests/generated/adversarial_negative.yaml
are loaded through the real suite loader; conflicting labels fail before dispatch.
Offline regression tests exercise discovery, analyzer and package entry points,
credential redaction in stdout/JSON/Markdown reports, and suite loading. These tests
are not evidence of live Claude trigger behavior. No live Claude observation is
claimed by this security contribution.
