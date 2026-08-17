# AGENTS.md

## Cursor Cloud specific instructions

This repository is a documentation + contracts project for the "Motor de Score Antifraude"
(fraud-score microservice). It contains ADRs, architecture docs, and versioned contracts
(OpenAPI + JSON Schema). There is **no application server, web UI, database, or test framework**
in this repo — the only runnable component is the contract validation script.

### Services / commands

- Validate / "build" / "test" / "run" (all the same single command):
  `python3 scripts/validate_contracts.py`
  It exits `0` when every contract is valid and `1` on any violation, printing the failing checks.
  It validates the event JSON Schema, the OpenAPI spec, that the documented event example matches
  the schema, that `ScoreResponseV1` stays restricted to `decision_final`, and that no contract
  exposes a plaintext CPF (LGPD guardrail). See `README.md` for context.
- Lint: none configured. Tests: none configured (the validation script is the de-facto test).

### Notes

- Dependencies come from `requirements-dev.txt` (jsonschema, PyYAML, openapi-spec-validator) and
  are installed by the update script. System Python 3 is used (no virtualenv is required).
- Docs and contracts are written in Portuguese; keep that language when editing them.
