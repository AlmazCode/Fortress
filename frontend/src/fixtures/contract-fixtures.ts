import source from '../../../contracts/fixtures.json';
import type { ApiTransport } from '../api/client';
import type { Diagnostics, Job } from '../api/types';

/** Canonical K examples. Import only from explicit tests or the guarded local fixture entry. */
export function fixtureCase(name: string): unknown {
  const item = source.cases.find(entry => entry.name === name);
  if (!item) throw new Error('Unknown test fixture');
  return structuredClone(item.payload);
}
export function createFixtureTransport(options: { enabled: boolean; outcome?: 'violation' | 'no_violation' | 'failed' }): ApiTransport {
  if (!options.enabled || import.meta.env.PROD) throw new Error('Synthetic transport requires explicit local test/demo mode');
  const jobs = new Map<string, number>([['00000000-0000-4000-8000-000000000001', 0]]);
  let sequence = 0;
  const json = (value: unknown, status = 200) =>
    new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
  const currentJob = (id: string): Job => ({ ...(fixtureCase((jobs.get(id) ?? 0) < 2 ? 'processing' : options.outcome ?? 'failed') as Job), job_id: id });
  return { fetch: async (input, init) => {
    if (init?.signal?.aborted) throw new DOMException('Aborted', 'AbortError');
    const path = typeof input === 'string' ? input : input instanceof URL ? input.pathname : input.url;
    if (path === '/api/ui/v1/model') return json(fixtureCase('model_status'));
    if (path === '/api/v1/analyze' && init?.method === 'POST') {
      const id = `00000000-0000-4000-8000-${String(++sequence).padStart(12, '0')}`;
      jobs.set(id, 0); return json({ job_id: id }, 202);
    }
    const publicId = /^\/api\/v1\/jobs\/([^/]+)$/.exec(path)?.[1];
    if (publicId && jobs.has(publicId)) {
      sequence = Math.max(sequence, Number(publicId.slice(-12)));
      jobs.set(publicId, jobs.get(publicId)! + 1); return json(currentJob(publicId));
    }
    const id = /^\/api\/ui\/v1\/jobs\/([^/]+)$/.exec(path)?.[1];
    if (id && jobs.has(id)) {
      const diagnostics = fixtureCase('ui_diagnostics') as Diagnostics;
      diagnostics.job_id = id; diagnostics.public = currentJob(id);
      diagnostics.stage = diagnostics.public.status === 'processing' ? 'inference' : diagnostics.public.status;
      diagnostics.processed_sec = diagnostics.public.status === 'processing' ? Math.min(diagnostics.duration_sec / 2, diagnostics.duration_sec) : diagnostics.duration_sec;
      if (diagnostics.public.status === 'done') {
        diagnostics.coverage = 'partial';
        if (diagnostics.timeline) diagnostics.timeline.coverage = 'partial';
      }
      return json(diagnostics);
    }
    return json({ error: { code: 'media_not_found', status: 404, message: 'Synthetic transport has no original video.' } }, 404);
  }};
}
