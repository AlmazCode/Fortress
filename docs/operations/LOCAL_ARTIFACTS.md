# Local artifacts and release boundaries

Set absolute `runtime_root` and `release_root` in a private copy of `config.example.toml`. Keep uploads, previews, frames, database/Redis volumes, annotations under development, cached features, checkpoints and trained releases outside tracked Git. An empty path means configuration is incomplete; never silently use the repository root. Each process must resolve and enforce its allowed local root, reject traversal/symlink escapes, and create bounded temporary files under that root.

Secrets come from the process environment or a private service secret mechanism: `FORTRESS_API_KEY`, `DATABASE_URL`, `REDIS_URL`. The tracked example contains no values. Use random internal filenames; original upload names are display data only. Do not log media, filesystem paths, API keys, database credentials or request bodies. Protect originals, previews and evidence frames with the same API authorization. The service must not contact cloud AI, download weights/packages at runtime, or analyze audio/faces.

## Durable acceptance and cleanup

Validate bounded upload/probe/decode, fsync the original, then atomically persist the job and outbox under the single unfinished-job capacity limit. Return 202 only after these steps are confirmed. A failed pre-accept request may remove its temporary files; a committed job survives client disconnect. Cleanup must check database ownership/reference state before deleting an original. Persistent user data and volumes are never removed to make a test pass. Deadline/retry failures remain inspectable failed records.

Worker leases use fencing tokens. Outbox publication is retryable and may duplicate delivery; only one current owner can persist one terminal result. Evidence must be 1–3 authentic JPEG frames taken from that job's original media at its recorded source PTS. The small synthetic contract JPEG is not a substitute for this source-binding check. Preview transformations preserve the original elapsed timeline and rotation; the UI's seek time must map back to the same original frame.

## Imported releases

A release is immutable and local: checkpoint, configuration, taxonomy, preprocessing, thresholds, metrics and model card, with versioned dataset/split/annotation/rules and a manifest of relative paths, measured byte sizes and SHA-256 hashes. Reject absolute/traversing paths, duplicate/omitted artifacts, symlink escapes, oversized inputs, incompatible versions/shapes/features and changed hashes. Compare the manifest configuration/preprocessing/taxonomy to the serialized descriptor before loading. Use bounded safe tensor/state-dict loading; a claimed hash does not itself make an untrusted package safe.

Production accepts only a trained, compatible, validated release with final taxonomy and verified provenance. Untrained, synthetic/test-only or incomplete packages are rejected. No production fallback to random weights or fixtures is permitted. Without a usable release, model diagnostics are `not_ready` and analyze returns 503 `model_not_ready`. Tiny CPU smoke releases and example hashes remain clearly test-only. Full training, independent dataset/ML evaluation, production model-size budgets and measured target-GPU resources are deferred to the separately authorized future stage.

## Reproduction and handoff

From the checked Git root run `uv sync --locked --group test`, then `uv run --locked --group test python -m pytest tests/contracts/test_schemas.py -q`. Record the actual SHA, command, exit code and environment for later task integration. A passing contract check validates software formats, not the availability of PostgreSQL/Redis/Docker, a trained model, external TLS, or real model accuracy/latency.

Local coordination checkpoints live under `.aster/checkpoints/` and are excluded through the checkout's Git exclude configuration. They are not published. Add machine-specific virtualenvs/cache paths to local excludes, never commit their contents. Only the exact task-owned text artifacts belong in the checked branch. Before push, inspect staged paths and diff, including deletions and rename endpoints. GitHub is the current coordination channel; preserve the fixed 36-stage dependency graph and integrate only verified prerequisite commits.
