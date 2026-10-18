import { createElement } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { ApiClient, ApiError, sessionQueries, type ApiTransport } from './client';
import { MAX_MEDIA_BYTES, mediaPath, parseDiagnostics, parseJob, parseModel,
  type Diagnostics, type Job, type ModelStatusData } from './types';
import { ApiKeyForm } from '../components/ApiKeyForm';
import { createFixtureTransport, fixtureCase } from '../fixtures/contract-fixtures';

const id = '00000000-0000-4000-8000-000000000001';
const key = 'test-private-memory-key';
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
function transport(handler: (input: RequestInfo | URL, init?: RequestInit) => Response | Promise<Response>) {
  const fetch = vi.fn(handler);
  return { transport: { fetch } as ApiTransport, fetch };
}
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('K wire conformance', () => {
  test.each(['processing', 'violation', 'no_violation', 'failed', 'insufficient_evidence'])('accepts canonical %s', name => {
    expect(parseJob(fixtureCase(name), id).job_id).toBe(id);
  });
  test('keeps unknown, unsupported, null versions and provenance without turning them into absence', () => {
    const value = parseDiagnostics(fixtureCase('ui_diagnostics'), id);
    expect(value.coverage).toBe('none');
    expect(value.unknown).toEqual(['actor']);
    expect(value.unsupported).toEqual(['synthetic_rule']);
    expect(value.versions.annotations).toBeNull();
    expect(value.timeline?.findings[0].status).toBe('unknown');
    expect(value.timeline?.findings[0].source.verified).toBe(false);
    expect(value.provenance.kind).toBe('synthetic');
  });
  test.each(['queued', 'running', 'unknown'])('rejects internal/nonpublic status %s', status => {
    expect(() => parseJob({ job_id: id, status }, id)).toThrow();
  });
  test('rejects UI fields on public JSON, a mismatched id and a contradictory verdict', () => {
    const done = fixtureCase('violation') as Extract<Job, { status: 'done' }>;
    expect(() => parseJob({ ...done, stage: 'done' }, id)).toThrow();
    expect(() => parseJob({ ...done, job_id: '00000000-0000-4000-8000-000000000002' }, id)).toThrow();
    expect(() => parseJob({ ...done, verdict: 'no_violation' }, id)).toThrow();
    expect(() => parseJob({ status: 'processing' }, id)).toThrow();
  });
  test('rejects invalid frame data and more than three frames', () => {
    const done = fixtureCase('violation') as Extract<Job, { status: 'done' }>;
    const event = done.violations[0];
    event.evidence_frames[0].image_base64 = 'data:image/jpeg;base64,/9j/';
    expect(() => parseJob(done, id)).toThrow();
    const original = fixtureCase('violation') as Extract<Job, { status: 'done' }>;
    original.violations[0].evidence_frames = Array(4).fill(original.violations[0].evidence_frames[0]);
    expect(() => parseJob(original, id)).toThrow();
  });
  test('rejects zero-coverage done, reversed intervals and foreign-job media', () => {
    const diagnostic = fixtureCase('ui_diagnostics') as Diagnostics;
    diagnostic.public = fixtureCase('no_violation') as Job;
    expect(() => parseDiagnostics(diagnostic, id)).toThrow();
    const reversed = fixtureCase('ui_diagnostics') as Diagnostics;
    reversed.timeline!.observations[0].interval = { start_sec: 2, end_sec: 1, scene_id: 'test' };
    expect(() => parseDiagnostics(reversed, id)).toThrow();
    const foreign = fixtureCase('ui_diagnostics') as Diagnostics;
    foreign.media.preview = { url: mediaPath('00000000-0000-4000-8000-000000000002', 'preview'), max_bytes: 100, content_type: 'video/mp4' };
    expect(() => parseDiagnostics(foreign, id)).toThrow();
  });
  test('model status uses K status enum and cannot report ready for test-only/untrained data', () => {
    const notReady = parseModel(fixtureCase('model_status'));
    expect(notReady.status).toBe('not_ready');
    expect(() => parseModel({ ready: true })).toThrow();
    expect(() => parseModel({ ...notReady, status: 'ready', release_version: 'test', reason: null, test_only: true })).toThrow();
  });
});

describe('authenticated client and session lifecycle', () => {
  test('uses header-only key, no-store and redirect:error; never persists or logs it', async () => {
    const storage = vi.spyOn(Storage.prototype, 'setItem');
    const logs = vi.spyOn(console, 'log').mockImplementation(() => undefined);
    const errors = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const t = transport(() => json(fixtureCase('processing')));
    const client = new ApiClient(key, t.transport);
    await client.job(id);
    expect(t.fetch).toHaveBeenCalledWith('/api/v1/jobs/' + id, expect.objectContaining({
      headers: { 'X-API-Key': key }, redirect: 'error', credentials: 'same-origin', cache: 'no-store',
    }));
    expect(storage).not.toHaveBeenCalled();
    expect(JSON.stringify(logs.mock.calls) + JSON.stringify(errors.mock.calls)).not.toContain(key);
    expect(String(t.fetch.mock.calls[0][0])).not.toContain(key);
    client.dispose();
  });
  test.each([
    [400, 'invalid_request'], [401, 'invalid_key'], [404, 'job_not_found'],
    [413, 'upload_too_large'], [415, 'unsupported_media'], [429, 'capacity_exceeded'], [503, 'model_not_ready'],
  ])('maps K nested error %s without returning backend message', async (status, code) => {
    const t = transport(() => json({ error: { code, status, message: 'private path C:/private/' + key } }, status as number));
    const client = new ApiClient(key, t.transport);
    await expect(client.job(id)).rejects.toMatchObject({ code, status });
    try { await client.job(id); } catch (error) { expect((error as Error).message).not.toContain(key); }
    client.dispose();
  });
  test.each(['../secret', 'x?key=secret', 'not-a-uuid'])('rejects invalid job path %s before fetch', async badId => {
    const t = transport(() => json({}));
    await expect(new ApiClient(key, t.transport).job(badId)).rejects.toMatchObject({ code: 'invalid_job_id' });
    expect(t.fetch).not.toHaveBeenCalled();
  });
  test('reset rejects a late response even if transport ignores AbortSignal', async () => {
    let complete!: (value: Response) => void;
    const t = transport(() => new Promise<Response>(resolve => { complete = resolve; }));
    const client = new ApiClient(key, t.transport);
    const pending = client.job(id);
    client.dispose();
    expect(t.fetch.mock.calls[0][1]?.signal?.aborted).toBe(true);
    complete(json(fixtureCase('processing')));
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    await expect(client.model()).rejects.toMatchObject({ name: 'AbortError' });
    expect(t.fetch).toHaveBeenCalledTimes(1);
  });
  test('query cancellation removes only this session cache and has no key in query keys', async () => {
    const t = transport((_path, init) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    }));
    const client = new ApiClient(key, t.transport);
    client.queries.setQueryData(['unrelated'], 'keep');
    const options = sessionQueries.job(client, id);
    expect(JSON.stringify(options.queryKey)).not.toContain(key);
    const result = client.queries.fetchQuery(options).catch(error => error);
    client.dispose();
    await result;
    expect(client.queries.getQueryData(options.queryKey)).toBeUndefined();
    expect(client.queries.getQueryData(['unrelated'])).toBe('keep');
    expect(t.fetch.mock.calls[0][1]?.signal?.aborted).toBe(true);
  });
  test('key form clears the password after connect and invokes explicit reset', () => {
    const connect = vi.fn(), reset = vi.fn();
    const view = render(createElement(ApiKeyForm, { connected: false, onConnect: connect, onReset: reset }));
    const input = screen.getByLabelText('API-ключ') as HTMLInputElement;
    fireEvent.change(input, { target: { value: key } });
    fireEvent.submit(input.closest('form')!);
    expect(connect).toHaveBeenCalledWith(key);
    expect(input.value).toBe('');
    view.rerender(createElement(ApiKeyForm, { connected: true, onConnect: connect, onReset: reset }));
    fireEvent.click(screen.getByRole('button', { name: 'Сбросить ключ' }));
    expect(reset).toHaveBeenCalledOnce();
  });
  test('GET retry is bounded and a new session can resume an accepted job without another POST', async () => {
    let attempts = 0;
    const t = transport((_input, init) => {
      if (init?.method === 'POST') return json({ job_id: id }, 202);
      if (++attempts < 4) return Promise.reject(new TypeError('offline'));
      return json(fixtureCase('processing'));
    });
    const first = new ApiClient(key, t.transport);
    await first.upload(new File(['synthetic'], 'demo.mp4'), new AbortController().signal);
    first.dispose();
    const resumed = new ApiClient(key, t.transport);
    await expect(resumed.queries.fetchQuery({ ...sessionQueries.job(resumed, id), retryDelay: 0 }))
      .rejects.toMatchObject({ code: 'network' });
    expect(attempts).toBe(3);
    await expect(resumed.job(id)).resolves.toMatchObject({ status: 'processing' });
    expect(t.fetch.mock.calls.filter(call => call[1]?.method === 'POST')).toHaveLength(1);
    resumed.dispose();
  });
});

describe('durable acceptance and bounded protected media', () => {
  const file = () => new File(['synthetic-video'], 'test.mp4', { type: 'video/mp4' });
  test('POSTs multipart once, reports indeterminate upload, then only polls GET', async () => {
    const t = transport((_input, init) => init?.method === 'POST' ? json({ job_id: id }, 202) : json(fixtureCase('processing')));
    const client = new ApiClient(key, t.transport), progress = vi.fn();
    await expect(client.upload(file(), new AbortController().signal, progress)).resolves.toBe(id);
    await client.job(id); await client.job(id);
    expect(t.fetch.mock.calls.filter(call => call[1]?.method === 'POST')).toHaveLength(1);
    expect(t.fetch.mock.calls[0][1]?.body).toBeInstanceOf(FormData);
    expect(t.fetch.mock.calls[0][1]?.headers).toEqual({ 'X-API-Key': key });
    expect(progress.mock.calls[0][0].computable).toBe(false);
    expect(progress.mock.calls[1][0].loaded).toBe(file().size);
    client.dispose();
  });
  test('network failure cannot fall back to synthetic or retry the POST', async () => {
    const t = transport(() => Promise.reject(new TypeError('network')));
    await expect(new ApiClient(key, t.transport).upload(file(), new AbortController().signal)).rejects.toMatchObject({ code: 'upload_outcome_unknown' });
    expect(t.fetch).toHaveBeenCalledTimes(1);
  });
  test.each([200, 202])('unconfirmed response %s is not treated as a new job', async status => {
    const t = transport(() => json({ job_id: 'invalid' }, status));
    await expect(new ApiClient(key, t.transport).upload(file(), new AbortController().signal)).rejects.toMatchObject({ code: 'upload_outcome_unknown' });
    expect(t.fetch).toHaveBeenCalledTimes(1);
  });
  test('abort before acceptance sends no request and size limit is enforced locally', async () => {
    const t = transport(() => json({ job_id: id }, 202));
    const client = new ApiClient(key, t.transport), abort = new AbortController(); abort.abort();
    await expect(client.upload(file(), abort.signal)).rejects.toMatchObject({ name: 'AbortError' });
    const oversized = file(); Object.defineProperty(oversized, 'size', { value: MAX_MEDIA_BYTES + 1 });
    await expect(client.upload(oversized, new AbortController().signal)).rejects.toMatchObject({ code: 'upload_too_large', status: 413 });
    expect(t.fetch).not.toHaveBeenCalled();
  });
  test.each(['https://attacker.invalid/video', '/api/ui/v1/jobs/' + id + '/preview?key=x', '/api/../video', '/api/ui/v1/jobs/' + id + '/frames/1'])('refuses non-video route %s', async path => {
    const t = transport(() => new Response());
    await expect(new ApiClient(key, t.transport).media(path)).rejects.toMatchObject({ code: 'unsafe_media_url' });
    expect(t.fetch).not.toHaveBeenCalled();
  });
  test('caps streaming bytes even without Content-Length and cancels the stream', async () => {
    const cancel = vi.fn();
    const body = new ReadableStream<Uint8Array>({ start(controller) { controller.enqueue(new Uint8Array(4)); }, cancel });
    const t = transport(() => new Response(body, { headers: { 'Content-Type': 'video/mp4' } }));
    await expect(new ApiClient(key, t.transport).media(mediaPath(id, 'preview'), undefined, 3)).rejects.toMatchObject({ code: 'media_too_large' });
    expect(cancel).toHaveBeenCalled();
  });
  test('refuses declared oversized media before buffering and rejects an incorrect MIME', async () => {
    const t = transport(() => new Response(new Uint8Array(1), { headers: { 'Content-Type': 'video/mp4', 'Content-Length': String(MAX_MEDIA_BYTES + 1) } }));
    await expect(new ApiClient(key, t.transport).media(mediaPath(id, 'media'))).rejects.toMatchObject({ code: 'media_too_large' });
    const bad = transport(() => new Response('not-video', { headers: { 'Content-Type': 'text/html' } }));
    await expect(new ApiClient(key, bad.transport).media(mediaPath(id, 'preview'))).rejects.toMatchObject({ code: 'invalid_preview' });
  });
  test('reset cancels a stalled media stream and returns no Blob', async () => {
    const cancel = vi.fn();
    const body = new ReadableStream<Uint8Array>({ cancel });
    const t = transport(() => new Response(body, { headers: { 'Content-Type': 'video/mp4' } }));
    const client = new ApiClient(key, t.transport);
    const pending = client.media(mediaPath(id, 'preview'));
    const result = pending.catch(error => error);
    await new Promise(resolve => setTimeout(resolve, 0));
    client.dispose();
    expect(await result).toMatchObject({ name: 'AbortError' });
    expect(cancel).toHaveBeenCalled();
  });
  test('fixture transport requires an explicit opt-in and performs no network', async () => {
    expect(() => createFixtureTransport({ enabled: false })).toThrow();
    const external = vi.spyOn(globalThis, 'fetch');
    const client = new ApiClient(key, createFixtureTransport({ enabled: true }));
    await client.upload(file(), new AbortController().signal);
    expect((await client.job(id)).status).toBe('processing');
    expect((await client.job(id)).status).toBe('failed');
    expect(external).not.toHaveBeenCalled();
    client.dispose();
  });
});
