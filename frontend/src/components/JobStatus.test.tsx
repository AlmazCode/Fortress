import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { ApiClient, ApiError } from '../api/client';
import type { Job } from '../api/types';
import { fixtureCase } from '../fixtures/contract-fixtures';
import { JobStatus, useJobPolling } from './JobStatus';
const id = '00000000-0000-4000-8000-000000000001';
afterEach(cleanup);
const base = { checking: false, onResume: vi.fn(), onClear: vi.fn() };
test('resume validates UUID and requires auth', () => {
  const onResume = vi.fn(); const view = render(<JobStatus {...base} onResume={onResume} />);
  const input = screen.getByLabelText('ID задания'); fireEvent.change(input, { target: { value: '../unsafe' } }); fireEvent.submit(input.closest('form')!);
  expect(screen.getByRole('alert').textContent).toContain('UUID'); expect(onResume).not.toHaveBeenCalled();
  fireEvent.change(input, { target: { value: id } }); fireEvent.submit(input.closest('form')!); expect(onResume).toHaveBeenCalledExactlyOnceWith(id);
  view.rerender(<JobStatus {...base} authenticated={false} onResume={onResume} />); fireEvent.submit(input.closest('form')!); expect(onResume).toHaveBeenCalledTimes(1);
});
test.each([[400, 'invalid_request', 'отклонён'], [401, 'invalid_key', 'Ключ не принят'], [404, 'job_not_found', 'не найдено'], [413, 'upload_too_large', '200 МиБ'], [415, 'unsupported_media', 'не поддерживаются'], [429, 'capacity_exceeded', 'Сервис занят'], [503, 'model_not_ready', 'Модель не готова'], [undefined, 'network', 'сейчас неизвестно']] as const)('shows outcome %s and explicit retry', (status, code, text) => {
  const retry = vi.fn(); render(<JobStatus {...base} jobId={id} job={fixtureCase('processing') as Job} error={new ApiError(code, status)} onRetry={retry} />);
  expect(screen.getByRole('alert').textContent).toContain(text); expect(screen.getByRole('status').textContent).toContain('не подтверждено');
  fireEvent.click(screen.getByRole('button', { name: 'Повторить проверку' })); expect(retry).toHaveBeenCalledOnce();
});
test('failed reason and accepted job disclaimer are visible', () => {
  render(<JobStatus {...base} jobId={id} job={fixtureCase('insufficient_evidence') as Job} />);
  expect(screen.getByRole('status').textContent).toContain('Недостаточно'); expect(screen.getByText(/Прерывание связи не отменяет/)).toBeTruthy();
});
function Harness({ client }: { client: ApiClient }) {
  const query = useJobPolling(client, id, 20);
  return <JobStatus {...base} jobId={id} job={query.data} checking={query.isFetching} error={query.error} />;
}
test.each(['no_violation', 'failed'])('polls until %s then stops; never POSTs', async outcome => {
  let count = 0; const methods: (string | undefined)[] = [];
  const client = new ApiClient('test', { fetch: async (_input, init) => { methods.push(init?.method); return new Response(JSON.stringify(fixtureCase(++count === 1 ? 'processing' : outcome))); } });
  const view = render(<QueryClientProvider client={client.queries}><Harness client={client} /></QueryClientProvider>);
  await waitFor(() => expect(count).toBe(2)); await new Promise(resolve => setTimeout(resolve, 70)); expect(count).toBe(2);
  expect(methods.every(method => !method)).toBe(true); view.unmount(); client.dispose();
});
test('unmount cancels an in-flight polling request', async () => {
  let signal: AbortSignal | null | undefined;
  const client = new ApiClient('test', { fetch: async (_input, init) => { signal = init?.signal; return new Promise<Response>((_resolve, reject) => signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))); } });
  const view = render(<QueryClientProvider client={client.queries}><Harness client={client} /></QueryClientProvider>);
  await waitFor(() => expect(signal).toBeTruthy()); view.unmount(); expect(signal!.aborted).toBe(true); client.dispose();
});
