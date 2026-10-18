import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import type { ApiTransport } from './api/client';
import type { Diagnostics, Job, ModelStatusData } from './api/types';
import { fixtureCase, createFixtureTransport } from './fixtures/contract-fixtures';
const id = '00000000-0000-4000-8000-000000000001', secret = 'private-app-test-key';
const ready = (): ModelStatusData => ({ ...(fixtureCase('model_status') as ModelStatusData), status: 'ready', reason: null, release_version: 'test-release', trained: true, validated: true, test_only: false });
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const clients: QueryClient[] = [];
const OriginalURL = URL;
beforeEach(() => { vi.stubGlobal('URL', class extends OriginalURL { static createObjectURL = vi.fn(() => 'blob:app-test'); static revokeObjectURL = vi.fn(); }); });
afterEach(() => { cleanup(); clients.forEach(client => client.clear()); clients.length = 0; vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.unstubAllEnvs(); });
function mount(transport: ApiTransport, fixtureMode = false, apiTestMode = false) {
  const queries = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 }, mutations: { retry: false } } }); clients.push(queries);
  return render(<QueryClientProvider client={queries}><App transport={transport} fixtureMode={fixtureMode} apiTestMode={apiTestMode} pollMs={20} /></QueryClientProvider>);
}
async function connect() { fireEvent.change(screen.getByLabelText('API-ключ'), { target: { value: secret } }); fireEvent.click(screen.getByRole('button', { name: /Подключить/ })); await screen.findByRole('button', { name: 'Сбросить ключ' }); }
async function upload() {
  fireEvent.change(screen.getByLabelText('Видеофайлы'), { target: { files: [new File(['synthetic'], 'test.mp4', { type: 'video/mp4' })] } });
  await screen.findByText('test.mp4');
  await waitFor(() => expect((screen.getByRole('button', { name: /Начать анализ/ }) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole('button', { name: /Начать анализ/ }));
}
function server(options: { status?: number; code?: string; notReady?: boolean; outcome?: string; outage?: boolean } = {}) {
  let reads = 0, posts = 0, offline = !!options.outage;
  const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path === '/api/ui/v1/model') return json(options.notReady ? fixtureCase('model_status') : ready());
    if (init?.method === 'POST') { posts++; return options.status ? json({ error: { status: options.status, code: options.code, message: 'private/path/' + secret } }, options.status) : json({ job_id: id }, 202); }
    if (path === '/api/v1/jobs/' + id) { reads++; if (offline && reads > 1) throw new TypeError('offline'); return json(fixtureCase(reads === 1 ? 'processing' : options.outcome ?? 'violation')); }
    if (path === '/api/ui/v1/jobs/' + id) {
      const d = fixtureCase('ui_diagnostics') as Diagnostics;
      d.public = fixtureCase(reads < 2 || offline ? 'processing' : options.outcome ?? 'violation') as Job;
      d.stage = d.public.status === 'processing' ? 'inference' : d.public.status; d.coverage = 'partial';
      if (d.timeline) d.timeline.coverage = 'partial'; d.media.preview = { url: '/api/ui/v1/jobs/' + id + '/preview', content_type: 'video/mp4', max_bytes: 100 };
      return json(d);
    }
    if (path.endsWith('/preview')) return new Response(new Uint8Array([0, 1, 2]), { headers: { 'Content-Type': 'video/mp4' } });
    throw new Error('Unexpected test route');
  });
  return { transport: { fetch }, fetch, posts: () => posts, reads: () => reads, reconnect: () => { offline = false; } };
}
test('complete upload/poll/done/evidence path uses one POST and bounded authenticated video', async () => {
  const consoleErrors = vi.spyOn(console, 'error'); const s = server(), storage = vi.spyOn(Storage.prototype, 'setItem'); mount(s.transport); await connect(); await upload();
  await screen.findByRole('heading', { name: 'Результат получен' }); await screen.findByRole('img'); await screen.findByLabelText('Видео задания');
  const video = screen.getByLabelText('Видео задания') as HTMLVideoElement;
  Object.defineProperty(video, 'readyState', { configurable: true, value: 1 }); Object.defineProperty(video, 'duration', { configurable: true, value: 1 });
  fireEvent.loadedMetadata(video); video.currentTime = .5;
  fireEvent.click(screen.getByRole('button', { name: /Событие 1:/ })); expect(video.currentTime).toBe(0);
  expect(screen.getByRole('slider', { name: 'Позиция в видео' }).getAttribute('max')).toBe('1');
  expect(consoleErrors).not.toHaveBeenCalled(); expect(s.posts()).toBe(1); expect(screen.getByText(/Демонстрационный результат/)).toBeTruthy(); expect(storage).not.toHaveBeenCalled();
  expect(s.fetch.mock.calls.every(([path, init]) => !String(path).includes(secret) && (init?.headers as Record<string, string>)['X-API-Key'] === secret)).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: /Кадр 1,/ })); fireEvent.click(screen.getByRole('button', { name: 'Сбросить ключ' }));
  expect(screen.queryByLabelText('Видео задания')).toBeNull(); expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:app-test'); expect(screen.getByLabelText('API-ключ')).toBeTruthy();
});
test.each([[400, 'invalid_request', 'отклонён'], [413, 'upload_too_large', 'лимит'], [415, 'unsupported_media', 'не поддерживается'], [429, 'capacity_exceeded', 'Сервис занят'], [503, 'model_not_ready', 'Модель пока не готова']] as const)('upload rejection %s shows safe next action with no retry POST', async (status, code, text) => {
  const s = server({ status, code }); mount(s.transport); await connect(); await upload();
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain(text)); expect(screen.getByRole('alert').textContent).not.toContain(secret); expect(s.posts()).toBe(1); expect(screen.queryByText('Результат получен')).toBeNull();
  if (status === 503) expect((screen.getByRole('button', { name: /Продолжить/ }) as HTMLButtonElement).disabled).toBe(true);
});
test('401 resets the session and offers password re-entry', async () => {
  const s = server({ status: 401, code: 'invalid_key' }); mount(s.transport); await connect(); await upload();
  await screen.findByLabelText('API-ключ'); expect(screen.queryByRole('button', { name: 'Сбросить ключ' })).toBeNull(); expect(screen.getByText(/Ключ не принят. Введите/)).toBeTruthy(); expect(s.posts()).toBe(1);
});
test('production path without release remains not ready and cannot send a file or show fixtures', async () => {
  const s = server({ notReady: true }); mount(s.transport); await connect(); await screen.findByText('Не готова');
  fireEvent.change(screen.getByLabelText('Видеофайлы'), { target: { files: [new File(['synthetic'], 'waiting.mp4', { type: 'video/mp4' })] } }); await screen.findByText('waiting.mp4');
  expect((screen.getByRole('button', { name: /Начать анализ/ }) as HTMLButtonElement).disabled).toBe(true); expect(s.posts()).toBe(0); expect(screen.queryByText(/Демонстрационный результат/)).toBeNull(); expect(screen.getByText('Как подключить модель')).toBeTruthy();
});
test('outage after 202 retains job id, stops bounded retries and resumes via GET without POST', async () => {
  const s = server({ outage: true }); mount(s.transport); await connect(); await upload();
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('сейчас неизвестно'));
  expect(s.reads()).toBe(4); expect(screen.getByText(id)).toBeTruthy(); expect(s.posts()).toBe(1); expect(screen.queryByRole('img')).toBeNull();
  s.reconnect(); fireEvent.click(screen.getByRole('button', { name: 'Повторить проверку' })); await screen.findByRole('heading', { name: 'Результат получен' }); expect(s.posts()).toBe(1);
});
test('reset during pending acceptance aborts fetch and ignores a late 202', async () => {
  let accept!: (value: Response) => void; let signal: AbortSignal | null | undefined;
  const transport: ApiTransport = { fetch: async (_input, init) => init?.method === 'POST' ? (signal = init.signal, new Promise(resolve => { accept = resolve; })) : json(ready()) };
  mount(transport); await connect(); await upload(); await waitFor(() => expect(signal).toBeTruthy()); fireEvent.click(screen.getByRole('button', { name: 'Сбросить ключ' }));
  expect(signal!.aborted).toBe(true); accept(json({ job_id: id }, 202)); await Promise.resolve(); expect(screen.queryByText(id)).toBeNull(); expect(screen.getByLabelText('API-ключ')).toBeTruthy();
});
test('explicit demo can exercise synthetic outcome while visibly remaining untrained', async () => {
  mount(createFixtureTransport({ enabled: true, outcome: 'no_violation' }), true); await connect(); await upload();
  await screen.findByRole('heading', { name: 'Результат получен' }); expect(screen.getByRole('note').textContent).toContain('Деморежим'); expect(await screen.findByText(/Не все условия и правила удалось проверить/)).toBeTruthy(); expect(screen.queryByText('Можно начать анализ.')).toBeNull();
});
test('public failed remains failure with its reason, no synthetic clean verdict', async () => {
  const s = server({ outcome: 'insufficient_evidence' }); mount(s.transport); await connect(); await upload(); await screen.findByRole('heading', { name: 'Анализ не завершён' }); expect(screen.getAllByText(/Недостаточно данных для анализа/).length).toBeGreaterThan(0); expect(screen.queryByRole('img')).toBeNull(); expect(s.posts()).toBe(1);
});

test('explicit API test mode requires server test_only; normal untrained production remains blocked', async () => {
  const notReady = fixtureCase('model_status') as ModelStatusData;
  const transport: ApiTransport = { fetch: async () => json({ ...notReady, test_only: true }) };
  mount(transport, false, true); await connect();
  fireEvent.change(screen.getByLabelText('Видеофайлы'), { target: { files: [new File(['test'], 'test.mp4', { type: 'video/mp4' })] } });
  await waitFor(() => expect((screen.getByRole('button', { name: /Начать анализ/ }) as HTMLButtonElement).disabled).toBe(false));
  expect(screen.getByRole('note').textContent).toContain('Тестовый API'); expect(screen.queryByText('Можно начать анализ.')).toBeNull();
});
test('API test flag does not bypass normal production not_ready', async () => {
  mount(server({ notReady: true }).transport, false, true); await connect(); await screen.findByText('Как подключить модель');
  fireEvent.change(screen.getByLabelText('Видеофайлы'), { target: { files: [new File(['test'], 'test.mp4', { type: 'video/mp4' })] } }); await screen.findByText('test.mp4');
  expect((screen.getByRole('button', { name: /Начать анализ/ }) as HTMLButtonElement).disabled).toBe(true);
});
test('production runtime ignores API-test and fixture props even with test-only transport', async () => {
  vi.stubEnv('PROD', true);
  const model = fixtureCase('model_status') as ModelStatusData;
  mount({ fetch: async () => json({ ...model, test_only: true }) }, true, true); await connect(); await screen.findByText('Тестовая');
  fireEvent.change(screen.getByLabelText('Видеофайлы'), { target: { files: [new File(['test'], 'test.mp4', { type: 'video/mp4' })] } }); await screen.findByText('test.mp4');
  expect((screen.getByRole('button', { name: /Начать анализ/ }) as HTMLButtonElement).disabled).toBe(true); expect(screen.queryByRole('note')).toBeNull();
});

test('files added before authentication survive connect, complete sequentially and expose their own results', async () => {
  const transport = createFixtureTransport({ enabled: true, outcome: 'violation' });
  const fetch = vi.spyOn(transport, 'fetch'); mount(transport, true);
  fireEvent.change(screen.getByLabelText('Видеофайлы'), { target: { files: [new File(['one'], 'first.mp4', { type: 'video/mp4' }), new File(['two'], 'second.mov', { type: 'video/quicktime' })] } });
  await screen.findByText('first.mp4'); expect(fetch).not.toHaveBeenCalled();
  expect((screen.getByRole('button', { name: /Начать анализ/ }) as HTMLButtonElement).disabled).toBe(true);
  await connect(); expect(screen.getByText('second.mov')).toBeTruthy();
  await waitFor(() => expect((screen.getByRole('button', { name: /Начать анализ/ }) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole('button', { name: /Начать анализ/ }));
  const region = screen.getByRole('region', { name: 'Очередь видео' });
  await within(region).findByText('Готово 2 из 2');
  expect(fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(2);
  expect(within(region).getAllByRole('listitem')).toHaveLength(2);
  fireEvent.click(screen.getByRole('button', { name: 'Открыть second.mov' }));
  await screen.findByText('00000000-0000-4000-8000-000000000002');
  fireEvent.click(screen.getByRole('button', { name: 'Открыть first.mp4' }));
  await screen.findByText('00000000-0000-4000-8000-000000000001');
});

test('readiness can be refreshed after a model is imported without losing waiting videos', async () => {
  let imported = false;
  const fetch = vi.fn(async () => json(imported ? ready() : fixtureCase('model_status')));
  mount({ fetch }); await connect(); await screen.findByText('Не готова');
  fireEvent.change(screen.getByLabelText('Видеофайлы'), { target: { files: [new File(['one'], 'waiting.mp4', { type: 'video/mp4' })] } });
  await screen.findByText('waiting.mp4'); expect((screen.getByRole('button', { name: /Начать анализ/ }) as HTMLButtonElement).disabled).toBe(true);
  imported = true; fireEvent.click(screen.getByRole('button', { name: 'Проверить готовность' }));
  await waitFor(() => expect((screen.getByRole('button', { name: /Начать анализ/ }) as HTMLButtonElement).disabled).toBe(false));
  expect(screen.getByText('waiting.mp4')).toBeTruthy(); expect(fetch).toHaveBeenCalledTimes(2);
});
