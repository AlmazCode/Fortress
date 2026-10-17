# Stack and compatibility contract 1.0

The personal assignment and the merged project brief select this stack. The older local Fortress v1.0 document describes a different SQLite/four-view design and is not the implementation contract for this graph.

| Layer | Contract |
|---|---|
| Runtime | Python 3.11; `pyproject.toml` + `uv.lock` are shared across backend, ML and rules |
| API | FastAPI, Pydantic v2, multipart upload; validation errors map to the documented HTTP 400 envelope, not an accidental 422 response |
| Persistence | PostgreSQL, SQLAlchemy 2, psycopg 3, Alembic; database is authoritative |
| Dispatch | Transactional outbox, Celery, Redis; concurrency 1, prefetch 1, bounded CPU threads |
| Video | Local FFmpeg/ffprobe and PyAV; decode presentation timestamps and preserve source origin/rotation |
| ML | TorchVision MobileNetV3-Small IMAGENET1K_V1 features + spatial average pool, assert 576; frozen encoder, one-layer GRU hidden 256, linear action head |
| Frontend | React/TypeScript/Vite/Tailwind/TanStack Query/Dropzone; role 2 owns its package-lock and builds without CDN |
| Deployment | Compose: nginx/api/worker/redis/postgres; persistent local volumes, worker without internet; GPU available only to worker |

`uv.lock` fixes the resolved Python versions and hashes. The default dependency set plus `test` group is for CPU software checks; optional `ml` includes the shared ML tools. Linux/Windows Torch wheels currently use the explicit official CPU index for reproducible smoke checks. This is not a CUDA/GPU readiness claim. O1 must actually verify target GPU, driver, CUDA toolkit/container runtime and compatible wheels before a GPU configuration is approved. Changes to this shared lock must be coordinated with role 1, not forked into four incompatible manifests. No package or weight download may happen during analysis.

From the project Git root:

```sh
uv sync --locked --group test
uv run --locked --group test python -m pytest tests/contracts/test_schemas.py -q
# Optional CPU ML environment, when needed by the ML task:
uv sync --locked --group test --extra ml
```

The contract check is software validation. It does not start a server, train a model, validate PostgreSQL/Redis persistence, or certify GPU/latency/ML accuracy. A1/A4 need real PostgreSQL/Redis tests; I/U/E/B/Z own integration, browser and operational evidence. Current default production behavior without an imported trained, compatible, independently validated release must be 503 `model_not_ready` before accepting a job.

## Formats and ownership

Canonical JSON Schema files use Draft 2020-12 and versioned offline IDs. `python_ports.validate_contract` resolves references from this directory only. OpenAPI 3.1 bundles those schemas so client generators do not fetch external references. Change both representations and validate them together. `fixtures.json` is explicitly synthetic/test-only, including a real decodable 16×16 JPEG; its zero SHA-256 values are placeholders, not measured artifact hashes. Fixtures must never be exposed as production inference results.

Breaking serialized changes require a new contract major version and coordinated producer/consumer updates. Changes to preprocessing, taxonomy, rules, dataset, annotations and split each receive an explicit version; a release pins all of them. Store actual hashes alongside versions. Never silently relabel a draft taxonomy as the unknown 25 official action IDs.

`OWNERSHIP.md`, `DEPENDENCIES.md` and `OUTCOMES.md` preserve all 36 stages. GitHub branches/commits now coordinate the work by explicit user request; keep the task boundaries and real verification. Each participant pulls/fetches the checked prerequisite SHA into its own checkout, verifies the diff and integrates it before building a dependent stage. Do not infer acceptance from a branch name or a task description. No MCP call is required by the current workflow.

## Time, observations and outcomes

Baseline preprocessing is **one view, letterbox 224, 2 fps, 32 frames, 50% overlap**, ImageNet mean `[0.485, 0.456, 0.406]` and std `[0.229, 0.224, 0.225]`. Padding preserves the full image; it is not TorchVision's standard resize-256/center-crop-224 transform. Temporal sampling uses source elapsed presentation time `(PTS - origin_pts) * time_base`, retains the actual PTS mapping, and does not invent timestamps from frame index / average FPS. VFR, rotation and nonzero source origin need real synthetic-video checks in A2/A3/D4/M1.

The feature-cache identity includes at least source video SHA-256, dataset manifest SHA/version, split/annotation versions, canonical preprocessing JSON SHA/version, encoder architecture and exact weight SHA/version, dtype, feature dimension, and source-PTS/window index. Reuse only when these match; partial cache entries are never complete. Reset temporal/session state at scene boundaries. Unknown/padded targets are masked out of loss and metrics; an all-masked window is skipped safely, not labeled negative.

Temporal annotations carry intervals, explicit presence/verified absence/unknown, visibility, review status and source provenance. Object annotations use source-pixel `[x,y,width,height]` boxes and original PTS mapping. Reviewed annotations require a reviewer; known relations require known endpoints. Group/canonical video split is selected **before** windows; a group cannot cross train/dev-validation/final-test. Object data alone is not an action dataset or a selected object detector.

RuleFinding is `triggered`, `not_triggered` or `unknown`. Unsupported or unverified normative rules cannot produce an affirmative or negative normative conclusion. Absence requires visible conditions and enough of the relevant interval. Rule implementations still verify recognizer validity, actor/party relations, exceptions and complete stage boundaries; schema validity alone cannot establish these facts. Fully insufficient observable coverage gives a public `failed` / `insufficient_evidence`. Partial coverage stays explicit in diagnostics; public `done` has only `violation` or `no_violation`.

## Auth and media

All public/UI/job/media/frame routes require `X-API-Key`. The initial contract uses one configured shared key; this is not per-user tenancy. UI holds the key in tab memory only, uses authenticated fetch, builds a bounded Blob URL for playback and seek, and revokes it on replacement/reset/unmount. Never put the key in a URL, persistent browser storage, bundled JS, logs or source control. Whole-file media fetch is the baseline; HTTP Range authentication is not assumed by the HTML video element. Sources, intervals, stages, unknowns, versions and limitations live only in the separate UI diagnostics schema, never extra jury JSON fields.

Input admission enforces 200 MiB, 180 seconds, long edge ≤1920 and short edge ≤1080 in either orientation, ≤60 fps, and MP4/MOV with a supported codec. Bound the actual decoding work as well as metadata checks. Invalid request/decode before acceptance: 400; unsupported format/limits: 415; byte limit: 413; invalid key: 401; unknown ID/media: 404; occupied atomic capacity: 429; unusable model/infrastructure: 503. After durable acceptance, failures become durable failed jobs with a reason. Deadline is ≤240 seconds from acceptance; stale/late owners cannot commit success. Audio/face recognition/cloud analysis are outside scope.

## Primary sources actually read

- [FastAPI forms and files](https://fastapi.tiangolo.com/tutorial/request-forms-and-files/): multipart upload requires python-multipart; multipart bodies do not simultaneously carry a JSON request body. The endpoint and error mapping above are project decisions.
- [JSON Schema conditional validation](https://json-schema.org/understanding-json-schema/reference/conditionals): if/then/else constrains conditional payloads; discriminator presence must be explicit. Verdict/violations and production-readiness conditions follow this mechanism.
- [TorchVision MobileNetV3-Small](https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.mobilenet_v3_small.html): IMAGENET1K_V1 and its published normalization/resize-center-crop transform were inspected. Project letterbox is an explicit different preprocessing choice. Feature dimension 576 must be asserted by actual ML code; no target GPU or performance result is implied by the documentation.
