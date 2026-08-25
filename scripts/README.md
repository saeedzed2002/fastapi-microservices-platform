# Scripts

This directory contains repeatable developer, CI, migration, contract, and operational commands as implementation appears.

Scripts must:

- be safe to rerun where practical;
- use explicit targets and avoid broad destructive behavior;
- fail clearly and return non-zero status;
- avoid embedding secrets;
- document prerequisites and side effects;
- produce concise CI-friendly output;
- use the same locked toolchain as development and CI.

Phase 0 provides `validate_phase0.ps1`, a project-dependency-free structural gate for JSON syntax, Markdown links and fences, whitespace, contract-catalog invariants, canonical envelope examples, and the minimal CI security baseline.

It requires PowerShell `7.4` or later with `Test-Json -SchemaFile`, whose schema engine supports the repository's Draft `2020-12` contracts; `Windows PowerShell 5.1` is not supported. Run it from the repository root:

```powershell
pwsh -NoProfile -File ./scripts/validate_phase0.ps1
```

It does not replace runtime, schema-compatibility, integration, container, security, or deployment validation introduced in later phases.
