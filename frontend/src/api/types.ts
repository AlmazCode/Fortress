import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import jobSchema from '../../../contracts/job.schema.json';
import diagnosticsSchema from '../../../contracts/diagnostics.schema.json';
import eventsSchema from '../../../contracts/events.schema.json';

export interface EvidenceFrame { timestamp_sec: number; image_base64: string }
export interface Violation {
  type: string; timecode_sec: number; description: string; evidence_frames: EvidenceFrame[];
}
export type FailureReason = 'insufficient_evidence' | 'deadline_exceeded' | 'decode_failed' |
  'inference_failed' | 'evidence_failed' | 'worker_lost' | 'internal_error' | 'release_invalid';
export type Job =
  | { job_id: string; status: 'processing' }
  | { job_id: string; status: 'done'; verdict: 'violation' | 'no_violation'; violations: Violation[] }
  | { job_id: string; status: 'failed'; reason: FailureReason };
export type Coverage = 'full' | 'partial' | 'none';
export type RuleState = 'triggered' | 'not_triggered' | 'unknown';
export interface Interval { start_sec: number; end_sec: number; scene_id: string }
export interface RuleSource {
  title?: string;
  source_kind: 'official' | 'internal_policy' | 'synthetic' | 'unverified';
  url: string | null; revision: string | null; section: string | null;
  snapshot_sha256: string | null; verified: boolean; limitations: string[];
}
export interface Finding {
  rule_id: string; status: RuleState; interval: Interval; actor_id: string | null;
  reason: string; support: 'supported' | 'unsupported'; observability: Coverage; source: RuleSource;
}
export interface Observation {
  class_id: string; interval: Interval; score: number | null;
  state: 'present' | 'absent_verified' | 'unknown' | 'unreviewed';
  known_mask: boolean; visibility: 'visible' | 'partial' | 'occluded' | 'unknown'; actor_id: string | null;
  relations: { kind: string; subject_id: string | null; object_id: string | null; known: boolean }[];
}
export interface Timeline {
  schema_version: '1.0'; video_id: string; scene_id: string; preprocessing_version: string;
  model_version: string; coverage: Coverage; observations: Observation[]; findings: Finding[];
}
export interface MediaDescriptor {
  url: string; content_type: 'video/mp4' | 'video/quicktime' | 'image/jpeg'; max_bytes: number;
}
/** Wire format from K; UI data stays separate from the public jury Job. */
export interface Diagnostics {
  schema_version: '1.0'; job_id: string; public: Job;
  stage: 'validation' | 'queued' | 'decoding' | 'inference' | 'rules' | 'evidence' | 'done' | 'failed';
  processed_sec: number | null; duration_sec: number; coverage: Coverage;
  unknown: string[]; unsupported: string[]; limitations: string[];
  versions: Record<'dataset' | 'annotations' | 'split' | 'rules' | 'model' | 'preprocessing' | 'taxonomy', string | null>;
  timeline: Timeline | null;
  media: { original: MediaDescriptor | null; preview: MediaDescriptor | null };
  provenance: { kind: 'original' | 'synthetic'; source_id: string; sha256: string };
}
export interface ModelStatusData {
  schema_version: '1.0'; status: 'ready' | 'not_ready' | 'prototype'; reason: string | null;
  release_version: string | null; trained: boolean; validated: boolean; test_only: boolean;
  limitations: string[];
}
export interface ErrorEnvelope { error: { code: string; status: number; message: string } }
export interface UploadProgress { loaded: number; total: number; computable: boolean }
export const MAX_MEDIA_BYTES = 200 * 1024 * 1024;
export const MEDIA_LIMITS = 'MP4 или MOV · до 200 МиБ · до 180 с · 1920×1080 или 1080×1920 · до 60 fps';

// Offline, synchronous schema registry: compileAsync/loadSchema are deliberately absent.
// strict:false accepts K's valid conditional schemas; coercion/defaults/removal stay disabled.
const validator = new Ajv2020({ strict: false, allErrors: false, coerceTypes: false,
  useDefaults: false, removeAdditional: false });
addFormats(validator);
validator.addSchema(jobSchema).addSchema(eventsSchema).addSchema(diagnosticsSchema);
const checkJob = validator.compile<Job>({ $ref: jobSchema.$id });
const checkDiagnostics = validator.compile<Diagnostics>({ $ref: diagnosticsSchema.$id + '#/$defs/Job' });
const checkModel = validator.compile<ModelStatusData>({ $ref: diagnosticsSchema.$id + '#/$defs/Model' });
const checkError = validator.compile<ErrorEnvelope>({ $ref: diagnosticsSchema.$id + '#/$defs/Error' });
const checkAccepted = validator.compile<{ job_id: string }>({ $ref: jobSchema.$id + '#/$defs/Accepted' });

export function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
export function validJobId(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}
export function parseAccepted(value: unknown): string {
  if (!checkAccepted(value)) throw new Error('Invalid acceptance response');
  return value.job_id;
}
export function parseJob(value: unknown, id: string): Job {
  if (!checkJob(value) || value.job_id !== id) throw new Error('Invalid public job');
  return value;
}
export function parseModel(value: unknown): ModelStatusData {
  if (!checkModel(value)) throw new Error('Invalid model readiness');
  return value;
}
export function parseError(value: unknown, status: number): ErrorEnvelope | undefined {
  return checkError(value) && value.error.status === status ? value : undefined;
}
export function isModelReady(model: ModelStatusData | undefined): boolean {
  return !!model && model.status === 'ready' && model.trained && model.validated && !model.test_only;
}
export function isPrototypeAvailable(model: ModelStatusData | undefined): boolean {
  return !!model && model.status === 'prototype' && model.trained && !model.validated && !model.test_only;
}
export function parseDiagnostics(value: unknown, id: string): Diagnostics {
  if (!checkDiagnostics(value) || value.job_id !== id || value.public.job_id !== id)
    throw new Error('Invalid diagnostics job');
  if (value.coverage === 'none' && value.public.status === 'done')
    throw new Error('Unobservable completion');
  for (const descriptor of [value.media.original, value.media.preview]) {
    if (descriptor && ![mediaPath(id, 'media'), mediaPath(id, 'preview')].includes(descriptor.url))
      throw new Error('Media belongs to another job or unsupported route');
  }
  for (const item of [...(value.timeline?.observations ?? []), ...(value.timeline?.findings ?? [])]) {
    if (item.interval.end_sec < item.interval.start_sec) throw new Error('Reversed source interval');
  }
  return value;
}
export function mediaPath(id: string, kind: 'media' | 'preview'): string {
  if (!validJobId(id)) throw new Error('Invalid job id');
  return '/api/ui/v1/jobs/' + id + '/' + kind;
}
export function isMediaPath(path: string): boolean {
  const match = /^\/api\/ui\/v1\/jobs\/([^/]+)\/(media|preview)$/.exec(path);
  return !!match && validJobId(match[1]);
}
export function formatTime(time: number): string {
  const whole = Math.floor(Math.max(0, time));
  return Math.floor(whole / 60).toString().padStart(2, '0') + ':' + (whole % 60).toString().padStart(2, '0');
}
