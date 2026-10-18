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
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); (this.querySelector('button,input') as HTMLElement | null)?.focus(); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
});
beforeEach(() => {
  vi.stubGlobal('URL', class extends OriginalURL { static createObjectURL = vi.fn(() => 'blob:app-test'); static revokeObjectURL = vi.fn(); });
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {});
});
afterEach(() => { cleanup(); clients.forEach(client => client.clear()); clients.length = 0; vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.unstubAllEnvs(); });
function mount(transport: ApiTransport, fixtureMode = false, apiTestMode = false) {
  const queries = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 }, mutations: { retry: false } } }); clients.push(queries);
  return render(<QueryClientProvider client={queries}><App transport={transport} fixtureMode={fixtureMode} apiTestMode={apiTestMode} pollMs={20} /></QueryClientProvider>);
}
function settings() {
  if (!screen.queryByRole('dialog', { name: 'Настройки' })) fireEvent.click(screen.getByRole('button', { name: 'Настройки' }));
  return screen.getByRole('dialog', { name: 'Настройки' });
}
async function connect() {
  const panel = settings(); fireEvent.change(within(panel).getByLabelText('API-ключ'), { target: { value: secret } });
  fireEvent.click(within(panel).getByRole('button', { name: 'Подключить' })); await screen.findByText('Доступ подключён');
  fireEvent.click(within(panel).getByRole('button', { name: 'Закрыть настройки' }));
}
async function add(files = [new File(['synthetic'], 'test.mp4', { type: 'video/mp4' })]) {
  fireEvent.change(screen.getByLabelText('Видеофайлы'), { target: { files } }); await screen.findByText(files[0].name);
}
async function start() {
  await waitFor(() => expect((screen.getByRole('button', { name: /Начать анализ/ }) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole('button', { name: /Начать анализ/ }));
}
async function viewResult(name = 'test.mp4') {
  fireEvent.click(await screen.findByRole('button', { name: `Открыть результат ${name}` }));
  return screen.findByRole('region', { name: 'Просмотр результата видео' });
}
function server(options: { status?: number; code?: string; notReady?: boolean; outcome?: string; outage?: boolean } = {}) {
  let reads = 0, posts = 0, offline = !!options.outage;
  const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path === '/api/ui/v1/model') return json(options.notReady ? fixtureCase('model_status') : ready());
    if (init?.method === 'POST') { posts++; return options.status ? json({ error: { status: options.status, code: options.code, message: 'private/path/' + secret } }, options.status) : json({ job_id: id }, 202); }
    if (path === '/api/v1/jobs/' + id) { reads++; if (offline && reads > 1) throw new TypeError('offline'); return json(fixtureCase(reads === 1 ? 'processing' : options.outcome ?? 'violation')); }
    if (path === '/api/ui/v1/jobs/' + id) {
      const d = fixtureCase('ui_diagnostics') as Diagnostics; d.public = fixtureCase(reads < 2 || offline ? 'processing' : options.outcome ?? 'violation') as Job;
      d.stage = d.public.status === 'processing' ? 'inference' : d.public.status; d.coverage = 'partial';
      if (d.timeline) d.timeline.coverage = 'partial'; d.media.preview = { url: '/api/ui/v1/jobs/' + id + '/preview', content_type: 'video/mp4', max_bytes: 100 }; return json(d);
    }
    if (path.endsWith('/preview')) return new Response(new Uint8Array([0, 1, 2]), { headers: { 'Content-Type': 'video/mp4' } });
    throw new Error('Unexpected test route');
  });
  return { transport: { fetch }, fetch, posts: () => posts, reads: () => reads, reconnect: () => { offline = false; } };
}
test('upload, sequential status, explicit result opening and event seek use one POST and protected media', async () => {
  const consoleErrors = vi.spyOn(console, 'error'), storage = vi.spyOn(Storage.prototype, 'setItem'); const s = server(); mount(s.transport);
  await connect(); await add(); await start();
  await screen.findByRole('button', { name: 'Открыть результат test.mp4' });
  expect(screen.queryByRole('region', { name: 'Просмотр результата видео' })).toBeNull();
  await viewResult(); const video = await screen.findByLabelText('Видео задания') as HTMLVideoElement;
  await screen.findByRole('img'); Object.defineProperty(video, 'readyState', { configurable: true, value: 1 }); Object.defineProperty(video, 'duration', { configurable: true, value: 1 });
  fireEvent.loadedMetadata(video); video.currentTime = .5; fireEvent.click(screen.getByRole('button', { name: /Событие 1:/ })); expect(video.currentTime).toBe(0);
  expect(screen.getByText('Возможное нарушение')).toBeTruthy(); expect(s.posts()).toBe(1); expect(storage).not.toHaveBeenCalled();
  expect(s.fetch.mock.calls.every(([path, init]) => !String(path).includes(secret) && (init?.headers as Record<string, string>)['X-API-Key'] === secret)).toBe(true);
  const panel = settings(); fireEvent.click(within(panel).getByRole('button', { name: 'Сбросить ключ' }));
  expect(screen.queryByLabelText('Видео задания')).toBeNull(); expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:app-test'); expect(screen.getByLabelText('API-ключ')).toBeTruthy();
  expect(consoleErrors).not.toHaveBeenCalled();
});
test.each([[400, 'invalid_request', 'отклонён'], [413, 'upload_too_large', 'лимит'], [415, 'unsupported_media', 'не поддерживается'], [429, 'capacity_exceeded', 'Сервис занят'], [503, 'model_not_ready', 'Модель пока не готова']] as const)('upload rejection %s is actionable and does not retry POST', async (status, code, text) => {
  const s = server({ status, code }); mount(s.transport); await connect(); await add(); await start();
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain(text)); expect(screen.getByRole('alert').textContent).not.toContain(secret); expect(s.posts()).toBe(1);
  expect(screen.queryByRole('button', { name: /Открыть результат/ })).toBeNull();
  if (status === 503) expect((screen.getByRole('button', { name: /Продолжить/ }) as HTMLButtonElement).disabled).toBe(true);
});
test('401 reopens settings for a new key and clears the previous session', async () => {
  const s = server({ status: 401, code: 'invalid_key' }); mount(s.transport); await connect(); await add(); await start();
  const input = await screen.findByLabelText('API-ключ'); expect(screen.getByRole('dialog', { name: 'Настройки' }).contains(input)).toBe(true);
  expect(screen.getByText(/Ключ не принят. Введите/)).toBeTruthy(); expect(s.posts()).toBe(1); expect(screen.queryByRole('button', { name: 'Сбросить ключ' })).toBeNull();
});
test('production without a validated release keeps queued files and cannot send or show fake results', async () => {
  const s = server({ notReady: true }); mount(s.transport); await connect(); await add();
  expect((screen.getByRole('button', { name: /Начать анализ/ }) as HTMLButtonElement).disabled).toBe(true); expect(s.posts()).toBe(0);
  expect(screen.getByText('Результаты появятся здесь после обработки видео')).toBeTruthy(); expect(screen.queryByText(/Демонстрационный результат/)).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Открыть настройки' })); expect(screen.getByText('Как подключить модель')).toBeTruthy();
});

test('prototype quality text comes from the model response rather than a hardcoded percentage', async () => {
  const model: ModelStatusData = { ...ready(), status: 'prototype', reason: 'experimental_model', validated: false,
    limitations: ['Средняя grouped accuracy: 75.00%; независимая проверка не выполнена.'] };
  mount({ fetch: async () => json(model) });
  await connect();
  expect(screen.getByText(/Локальный прототип\./).textContent).toContain('75.00%');
  expect(screen.queryByText(/точность около 71%/)).toBeNull();
});
test('lost GET after 202 stops bounded retries and restores state without a new POST', async () => {
  const s = server({ outage: true }); mount(s.transport); await connect(); await add(); await start();
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('сейчас неизвестно'));
  expect(s.reads()).toBe(4); expect(s.posts()).toBe(1); expect(screen.queryByRole('button', { name: /Открыть результат/ })).toBeNull();
  s.reconnect(); fireEvent.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Проверить состояние' }));
  await screen.findByRole('button', { name: 'Открыть результат test.mp4' }); expect(s.posts()).toBe(1);
});
test('reset aborts pending acceptance and a late 202 cannot resurrect the queue', async () => {
  let accept!: (value: Response) => void; let signal: AbortSignal | null | undefined;
  const transport: ApiTransport = { fetch: async (_input, init) => init?.method === 'POST' ? (signal = init.signal, new Promise(resolve => { accept = resolve; })) : json(ready()) };
  mount(transport); await connect(); await add(); await start(); await waitFor(() => expect(signal).toBeTruthy());
  const panel = settings(); fireEvent.click(within(panel).getByRole('button', { name: 'Сбросить ключ' })); expect(signal!.aborted).toBe(true);
  accept(json({ job_id: id }, 202)); await Promise.resolve(); expect(screen.queryByRole('button', { name: /Открыть результат/ })).toBeNull();
});
test('no detections is distinct from empty results, while demo and analysis limits remain explicit', async () => {
  mount(createFixtureTransport({ enabled: true, outcome: 'no_violation' }), true); await connect(); await add(); await start();
  await screen.findByText('Возможные нарушения не обнаружены'); expect(screen.queryByText('Результаты появятся здесь после обработки видео')).toBeNull();
  expect(screen.getByRole('note').textContent).toContain('загруженные видео не анализируются'); await viewResult();
  expect(screen.getByRole('heading', { name: 'Возможные нарушения не обнаружены' })).toBeTruthy(); expect(screen.getByText(/Не все условия и правила удалось проверить/)).toBeTruthy();
});
test('failed analysis exposes its reason and a next action instead of a clean result', async () => {
  const s = server({ outcome: 'insufficient_evidence' }); mount(s.transport); await connect(); await add(); await start();
  await screen.findByText('Ошибка анализа'); expect(screen.getAllByText('Недостаточно данных для анализа.').length).toBeGreaterThan(0);
  expect(screen.getByRole('button', { name: 'Выбрать другое видео' })).toBeTruthy(); expect(screen.queryByRole('button', { name: /Открыть результат/ })).toBeNull(); expect(s.posts()).toBe(1);
});
test('test-only API permission is explicit, and normal untrained production stays blocked', async () => {
  const model = fixtureCase('model_status') as ModelStatusData;
  mount({ fetch: async () => json({ ...model, test_only: true }) }, false, true); await connect(); await add();
  await waitFor(() => expect((screen.getByRole('button', { name: /Начать анализ/ }) as HTMLButtonElement).disabled).toBe(false)); expect(screen.getByRole('note').textContent).toContain('Тестовый API');
});
test('API test flag cannot bypass an ordinary not-ready server', async () => {
  mount(server({ notReady: true }).transport, false, true); await connect(); await add();
  expect((screen.getByRole('button', { name: /Начать анализ/ }) as HTMLButtonElement).disabled).toBe(true);
});
test('production ignores demo and API-test props even with a test-only model', async () => {
  vi.stubEnv('PROD', true); const model = fixtureCase('model_status') as ModelStatusData;
  mount({ fetch: async () => json({ ...model, test_only: true }) }, true, true); await connect(); await add();
  expect((screen.getByRole('button', { name: /Начать анализ/ }) as HTMLButtonElement).disabled).toBe(true); expect(screen.queryByRole('note')).toBeNull();
});
test('files added before authentication survive settings and have independent result selection', async () => {
  const transport = createFixtureTransport({ enabled: true, outcome: 'violation' }); const fetch = vi.spyOn(transport, 'fetch'); mount(transport, true);
  await add([new File(['one'], 'first.mp4', { type: 'video/mp4' }), new File(['two'], 'second.mov', { type: 'video/quicktime' })]); expect(fetch).not.toHaveBeenCalled();
  await connect(); await start(); await screen.findByRole('button', { name: 'Открыть результат second.mov' });
  const overview = screen.getByRole('region', { name: 'Результаты анализа' }); expect(within(overview).getAllByRole('listitem')).toHaveLength(2);
  expect(fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(2);
  const view = await viewResult('second.mov'); expect(within(view).getByRole('heading', { name: 'second.mov' })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'К списку результатов' })); expect(screen.queryByRole('region', { name: 'Просмотр результата видео' })).toBeNull();
  expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Открыть результат second.mov' })); await viewResult('first.mp4');
});

test('clearing pending files preserves results and clearing results preserves pending files', async () => {
  const transport = createFixtureTransport({ enabled: true, outcome: 'violation' }); mount(transport, true);
  await connect(); await add(); await start(); await screen.findByRole('button', { name: 'Открыть результат test.mp4' });
  expect(screen.getByRole('button', { name: 'Добавить ещё видео' })).toBeTruthy();
  expect(screen.queryByRole('list', { name: 'Видео в очереди' })).toBeNull();
  await add([new File(['next'], 'next.mp4', { type: 'video/mp4' })]);
  fireEvent.click(screen.getByRole('button', { name: 'Очистить очередь' }));
  expect(screen.queryByText('next.mp4')).toBeNull(); expect(screen.getByRole('button', { name: 'Открыть результат test.mp4' })).toBeTruthy();
  await add([new File(['next'], 'next.mp4', { type: 'video/mp4' })]);
  fireEvent.click(screen.getByRole('button', { name: 'Очистить результаты' }));
  expect(screen.queryByRole('button', { name: 'Открыть результат test.mp4' })).toBeNull(); expect(screen.getByText('next.mp4')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Очистить очередь' }));
  expect(screen.getByRole('button', { name: 'Выбрать видео' })).toBeTruthy(); expect(screen.getByText('Перетащите видео сюда')).toBeTruthy();
});
test('model readiness can be refreshed without losing waiting files', async () => {
  let imported = false; mount({ fetch: async () => json(imported ? ready() : fixtureCase('model_status')) }); await connect(); await add();
  const panel = settings(); imported = true; fireEvent.click(within(panel).getByRole('button', { name: 'Проверить готовность' }));
  await within(panel).findByText('Можно начать анализ.'); fireEvent.click(within(panel).getByRole('button', { name: 'Закрыть настройки' }));
  expect((screen.getByRole('button', { name: /Начать анализ/ }) as HTMLButtonElement).disabled).toBe(false); expect(screen.getByText('test.mp4')).toBeTruthy();
});
test('drawer starts closed, contains access/model/job search, and closing preserves active analysis', async () => {
  const s = server(); mount(s.transport); expect(screen.queryByRole('dialog')).toBeNull(); expect(screen.queryByRole('heading', { name: 'Модель' })).toBeNull();
  expect(screen.getByText('Результаты появятся здесь после обработки видео')).toBeTruthy(); await add();
  fireEvent.click(screen.getByRole('button', { name: 'Открыть настройки' })); const panel = screen.getByRole('dialog', { name: 'Настройки' });
  expect(within(panel).getByLabelText('ID задания')).toBeTruthy(); expect(within(panel).getByText('Требуется ключ')).toBeTruthy();
  fireEvent(panel, new Event('cancel', { bubbles: false, cancelable: true })); expect(screen.queryByRole('dialog')).toBeNull();
  await connect(); await start(); await screen.findByRole('button', { name: 'Открыть результат test.mp4' });
  expect(screen.queryByRole('dialog')).toBeNull(); expect(s.posts()).toBe(1); expect(within(settings()).getByText('Доступ подключён')).toBeTruthy();
});
