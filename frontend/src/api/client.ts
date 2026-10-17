import { QueryClient, queryOptions } from '@tanstack/react-query';
import { MAX_MEDIA_BYTES, isMediaPath, parseAccepted, parseDiagnostics, parseError, parseJob,
  parseModel, validJobId, type UploadProgress } from './types';
export { validJobId } from './types';

export class ApiError extends Error {
  constructor(public readonly code: string, public readonly status?: number) {
    super(code); this.name = 'ApiError';
  }
}
export interface ApiTransport { fetch: typeof fetch }
let sessionSequence = 0;
const aborted = () => new DOMException('Session request aborted', 'AbortError');
const jobPath = (id: string) => {
  if (!validJobId(id)) throw new ApiError('invalid_job_id', 400);
  return encodeURIComponent(id);
};
const responseError = (status: number, value: unknown) =>
  new ApiError(parseError(value, status)?.error.code ?? 'request_failed', status);

export class ApiClient {
  readonly session = ++sessionSequence;
  private controllers = new Set<AbortController>();
  private destroyed = false;
  constructor(private key: string, private transport: ApiTransport = { fetch: (...args) => fetch(...args) },
    readonly queries = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })) {}
  dispose(): void {
    this.destroyed = true;
    this.controllers.forEach(controller => controller.abort());
    this.controllers.clear(); this.key = '';
    const filters = { predicate: (query: { queryKey: readonly unknown[] }) =>
      query.queryKey[0] === 'fortress' && query.queryKey[1] === this.session };
    void this.queries.cancelQueries(filters);
    this.queries.removeQueries(filters);
  }
  private async scoped<T>(operation: (signal: AbortSignal) => Promise<T>, external?: AbortSignal): Promise<T> {
    if (this.destroyed || external?.aborted) throw aborted();
    const controller = new AbortController(), abort = () => controller.abort();
    external?.addEventListener('abort', abort, { once: true });
    this.controllers.add(controller);
    try {
      const result = await operation(controller.signal);
      if (controller.signal.aborted || this.destroyed) throw aborted();
      return result;
    } finally {
      external?.removeEventListener('abort', abort); this.controllers.delete(controller);
    }
  }
  private async response(path: string, signal: AbortSignal, init: RequestInit = {}): Promise<Response> {
    try {
      return await this.transport.fetch(path, { ...init, signal, headers: { 'X-API-Key': this.key },
        redirect: 'error', credentials: 'same-origin', cache: 'no-store' });
    } catch {
      if (signal.aborted) throw aborted();
      throw new ApiError(init.method === 'POST' ? 'upload_outcome_unknown' : 'network');
    }
  }
  private async json(path: string, signal?: AbortSignal): Promise<unknown> {
    return this.scoped(async active => {
      const response = await this.response(path, active);
      if (!response.ok) throw responseError(response.status, await response.json().catch(() => undefined));
      try { return await response.json(); } catch { throw new ApiError('protocol'); }
    }, signal);
  }
  async model(signal?: AbortSignal) {
    const value = await this.json('/api/ui/v1/model', signal);
    try { return parseModel(value); } catch { throw new ApiError('protocol'); }
  }
  async job(id: string, signal?: AbortSignal) {
    const value = await this.json('/api/v1/jobs/' + jobPath(id), signal);
    try { return parseJob(value, id); } catch { throw new ApiError('protocol'); }
  }
  async diagnostics(id: string, signal?: AbortSignal) {
    const value = await this.json('/api/ui/v1/jobs/' + jobPath(id), signal);
    try { return parseDiagnostics(value, id); } catch { throw new ApiError('protocol'); }
  }
  async upload(file: File, signal: AbortSignal, progress?: (value: UploadProgress) => void): Promise<string> {
    if (file.size > MAX_MEDIA_BYTES) throw new ApiError('upload_too_large', 413);
    if (file.size === 0 || !/\.(mp4|mov)$/i.test(file.name)) throw new ApiError('unsupported_media', 415);
    // Browser fetch exposes no reliable upload byte progress: display an indeterminate
    // transfer, separate from processing. Report completion only after durable 202.
    progress?.({ loaded: 0, total: file.size, computable: false });
    return this.scoped(async active => {
      const form = new FormData(); form.append('file', file);
      const response = await this.response('/api/v1/analyze', active, { method: 'POST', body: form });
      if (response.status !== 202) {
        if (response.ok || response.status >= 500 && response.status !== 503)
          throw new ApiError('upload_outcome_unknown', response.status);
        throw responseError(response.status, await response.json().catch(() => undefined));
      }
      try {
        const id = parseAccepted(await response.json());
        if (active.aborted || this.destroyed) throw aborted();
        progress?.({ loaded: file.size, total: file.size, computable: true });
        return id;
      } catch (error) {
        if (active.aborted || this.destroyed) throw aborted();
        throw error instanceof ApiError ? error : new ApiError('upload_outcome_unknown', 202);
      }
    }, signal);
  }
  async media(path: string, signal?: AbortSignal, maxBytes = MAX_MEDIA_BYTES): Promise<Blob> {
    if (!isMediaPath(path) || !Number.isSafeInteger(maxBytes) || maxBytes < 1 || maxBytes > MAX_MEDIA_BYTES)
      throw new ApiError('unsafe_media_url');
    return this.scoped(async active => {
      const response = await this.response(path, active);
      if (!response.ok) throw responseError(response.status, await response.json().catch(() => undefined));
      const type = response.headers.get('content-type') ?? '';
      if (!/^video\/(mp4|quicktime)(;|$)/i.test(type)) {
        await response.body?.cancel(); throw new ApiError('invalid_preview');
      }
      const length = response.headers.get('content-length');
      if (length !== null && (!/^\d+$/.test(length) || Number(length) > maxBytes)) {
        await response.body?.cancel(); throw new ApiError('media_too_large', 413);
      }
      const reader = response.body?.getReader();
      if (!reader) throw new ApiError('invalid_preview');
      const parts: BlobPart[] = []; let bytes = 0;
      const cancelOnAbort = () => { void reader.cancel().catch(() => undefined); };
      active.addEventListener('abort', cancelOnAbort, { once: true });
      try {
        while (true) {
          if (active.aborted) throw aborted();
          const { done, value } = await reader.read();
          if (done) break;
          bytes += value.byteLength;
          if (bytes > maxBytes) throw new ApiError('media_too_large', 413);
          parts.push(value.slice().buffer);
        }
        return new Blob(parts, { type });
      } catch (error) {
        await reader.cancel().catch(() => undefined);
        throw error;
      } finally { active.removeEventListener('abort', cancelOnAbort); reader.releaseLock(); }
    }, signal);
  }
}
const retryRead = (count: number, error: unknown) => count < 2 && error instanceof ApiError && error.code === 'network';
export const sessionQueries = {
  model: (client: ApiClient) => queryOptions({
    queryKey: ['fortress', client.session, 'model'] as const,
    queryFn: ({ signal }) => client.model(signal), retry: retryRead,
  }),
  job: (client: ApiClient, id: string) => queryOptions({
    queryKey: ['fortress', client.session, 'job', id] as const,
    queryFn: ({ signal }) => client.job(id, signal), retry: retryRead,
  }),
  diagnostics: (client: ApiClient, id: string) => queryOptions({
    queryKey: ['fortress', client.session, 'diagnostics', id] as const,
    queryFn: ({ signal }) => client.diagnostics(id, signal), retry: retryRead,
  }),
};
