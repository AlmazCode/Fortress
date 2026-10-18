import { StrictMode, type ReactNode } from 'react';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiClient } from './api/client';
import type { Diagnostics, Job } from './api/types';
import { fixtureCase } from './fixtures/contract-fixtures';
import { MAX_QUEUE_FILES, useVideoQueue } from './useVideoQueue';

const clients: ApiClient[] = [];
afterEach(() => { cleanup(); clients.forEach(client => { client.dispose(); client.queries.clear(); }); clients.length = 0; });
const file = (name = 'one.mp4') => new File(['synthetic'], name, { type: 'video/mp4' });
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
const pause = () => new Promise(resolve => setTimeout(resolve, 70));

function server(options: { rejectPost?: 'network' | 'capacity'; deferred?: boolean } = {}) {
  const posts: string[] = [], jobs = new Map<string, Job>();
  let attempts = 0, offline = false, pending: ((response: Response) => void) | undefined;
  const queries = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } });
  const client = new ApiClient('private-queue-key', { fetch: async (input, init) => {
    const path = String(input);
    if (init?.method === 'POST') {
      posts.push(((init.body as FormData).get('file') as File).name); attempts++;
      if (attempts === 1 && options.rejectPost === 'network') throw new TypeError('offline');
      if (attempts === 1 && options.rejectPost === 'capacity') return json({ error: { status: 429, code: 'capacity_exceeded', message: 'Busy' } }, 429);
      const id = `00000000-0000-4000-8000-${String(attempts).padStart(12, '0')}`;
      jobs.set(id, { job_id: id, status: 'processing' });
      if (options.deferred && attempts === 1) return new Promise<Response>((resolve, reject) => {
        pending = resolve; init.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
      });
      return json({ job_id: id }, 202);
    }
    const id = path.split('/').at(-1)!;
    const job = jobs.get(id);
    if (!job) return json({ error: { code: 'job_not_found', status: 404, message: 'Missing' } }, 404);
    if (path.startsWith('/api/v1/')) { if (offline) throw new TypeError('offline'); return json(job); }
    const d = fixtureCase('ui_diagnostics') as Diagnostics;
    d.job_id = id; d.public = job; d.stage = job.status === 'processing' ? 'inference' : job.status;
    d.duration_sec = 10; d.processed_sec = 4; d.coverage = 'partial';
    return json(d);
  } }, queries);
  clients.push(client);
  const accepted = vi.fn();
  const wrapper = ({ children }: { children: ReactNode }) => <StrictMode><QueryClientProvider client={queries}>{children}</QueryClientProvider></StrictMode>;
  const view = renderHook(() => useVideoQueue({ client, ready: true, onAccepted: accepted, pollMs: 20 }), { wrapper });
  const finish = (id: string, failed = false) => jobs.set(id, failed ? { job_id: id, status: 'failed', reason: 'decode_failed' } : { ...(fixtureCase('violation') as Extract<Job, { status: 'done' }>), job_id: id });
  return { ...view, posts, jobs, finish, accepted, setOffline: (value: boolean) => { offline = value; }, acceptLate: () => pending?.(json({ job_id: [...jobs.keys()][0] }, 202)) };
}

test.each([false, true])('submits the next file only after a terminal server result (failed=%s), including StrictMode', async failed => {
  const s = server(); act(() => s.result.current.add([file(), file('two.mov')]));
  expect(s.posts).toHaveLength(0); act(() => s.result.current.start());
  await waitFor(() => expect(s.result.current.active?.state).toBe('processing'));
  expect(s.posts).toEqual(['one.mp4']); const first = s.result.current.active!.jobId!;
  await pause(); expect(s.posts).toHaveLength(1);
  s.finish(first, failed); await waitFor(() => expect(s.posts).toEqual(['one.mp4', 'two.mov']));
  expect(s.result.current.items[0].state).toBe(failed ? 'failed' : 'done');
  await waitFor(() => expect(s.result.current.active?.jobId).toBeTruthy());
  const second = s.result.current.active!.jobId!; expect(second).not.toBe(first);
  s.finish(second); await waitFor(() => expect(s.result.current.items[1].state).toBe('done'));
  expect(s.result.current.items.every(item => !item.file)).toBe(true);
});

test('pause lets an accepted job finish and holds the remaining local files', async () => {
  const s = server(); act(() => { s.result.current.add([file(), file('two.mp4')]); s.result.current.start(); });
  await waitFor(() => expect(s.result.current.active?.jobId).toBeTruthy());
  act(() => s.result.current.pause()); s.finish(s.result.current.active!.jobId!);
  await waitFor(() => expect(s.result.current.items[0].state).toBe('done'));
  await pause(); expect(s.posts).toHaveLength(1); expect(s.result.current.items[1].state).toBe('waiting');
  act(() => s.result.current.start()); await waitFor(() => expect(s.posts).toHaveLength(2));
});

test('an ambiguous POST pauses the queue and never resubmits the uncertain file', async () => {
  const s = server({ rejectPost: 'network' }); act(() => { s.result.current.add([file(), file('two.mp4')]); s.result.current.start(); });
  await waitFor(() => expect(s.result.current.items[0].state).toBe('uncertain'));
  await pause(); expect(s.posts).toEqual(['one.mp4']); expect(s.result.current.running).toBe(false);
  act(() => s.result.current.start()); await waitFor(() => expect(s.posts).toEqual(['one.mp4', 'two.mp4']));
});

test('capacity rejection retains the file and requires explicit retry', async () => {
  const s = server({ rejectPost: 'capacity' }); act(() => { s.result.current.add([file()]); s.result.current.start(); });
  await waitFor(() => expect(s.result.current.error).toBeTruthy());
  await pause(); expect(s.posts).toHaveLength(1); expect(s.result.current.items[0].state).toBe('waiting');
  act(() => s.result.current.start()); await waitFor(() => expect(s.result.current.active?.state).toBe('processing'));
  expect(s.posts).toEqual(['one.mp4', 'one.mp4']);
});

test('network loss after acceptance preserves the job and stops the next POST until recovery', async () => {
  const s = server(); act(() => { s.result.current.add([file(), file('two.mp4')]); s.result.current.start(); });
  await waitFor(() => expect(s.result.current.job.data?.status).toBe('processing'));
  const id = s.result.current.active!.jobId!; s.setOffline(true);
  await waitFor(() => expect(s.result.current.job.error).toBeTruthy());
  expect(s.result.current.active?.jobId).toBe(id); expect(s.posts).toHaveLength(1);
  s.setOffline(false); s.finish(id); act(() => s.result.current.start());
  await waitFor(() => expect(s.posts).toHaveLength(2));
});

test('aborting a transfer reports uncertainty and holds the next file', async () => {
  const s = server({ deferred: true }); act(() => { s.result.current.add([file(), file('two.mp4')]); s.result.current.start(); });
  await waitFor(() => expect(s.result.current.uploading).toBe(true));
  expect(s.result.current.progress?.computable).toBe(false); act(() => s.result.current.abort());
  await waitFor(() => expect(s.result.current.items[0].state).toBe('uncertain'));
  await pause(); expect(s.posts).toHaveLength(1);
});

test('clearing during upload ignores a late acceptance and releases every queued file', async () => {
  const s = server({ deferred: true }); act(() => { s.result.current.add([file(), file('two.mp4')]); s.result.current.start(); });
  await waitFor(() => expect(s.posts).toHaveLength(1)); act(() => s.result.current.clear());
  act(() => s.acceptLate()); await pause(); expect(s.result.current.items).toHaveLength(0);
  expect(s.posts).toHaveLength(1); expect(s.accepted).not.toHaveBeenCalled();
});

test('caps a batch and permits removing only files that have not started', async () => {
  const s = server(); act(() => s.result.current.add(Array.from({ length: 24 }, (_, i) => file(`${i}.mp4`))));
  expect(s.result.current.items).toHaveLength(MAX_QUEUE_FILES); expect(s.result.current.selectionNotice).toContain('20');
  act(() => s.result.current.remove(s.result.current.items[1].id)); expect(s.result.current.items).toHaveLength(19);
  act(() => s.result.current.start()); await waitFor(() => expect(s.result.current.active?.jobId).toBeTruthy());
  const current = s.result.current.active!.id; act(() => { s.result.current.remove(current); s.result.current.clearWaiting(); });
  expect(s.result.current.items).toHaveLength(1); expect(s.result.current.active?.id).toBe(current);
});

test('opening an existing accepted job holds queued uploads until that job finishes', async () => {
  const s = server(), id = '00000000-0000-4000-8000-000000000099';
  s.jobs.set(id, { job_id: id, status: 'processing' });
  act(() => { s.result.current.add([file()]); s.result.current.resume(id); });
  await waitFor(() => expect(s.result.current.job.data?.status).toBe('processing'));
  act(() => s.result.current.start()); await pause(); expect(s.posts).toHaveLength(0);
  s.finish(id); await waitFor(() => expect(s.posts).toEqual(['one.mp4']));
});
