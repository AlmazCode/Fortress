import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ApiError } from '../api/client';
import { ErrorPanel } from './ErrorPanel';
afterEach(cleanup);
test.each([[400, 'invalid_request', 'отклонён'], [401, 'invalid_key', 'Ключ не принят'], [404, 'job_not_found', 'не найдены'], [413, 'media_too_large', 'лимит'], [415, 'unsupported_media', 'не поддерживается'], [429, 'capacity_exceeded', 'Сервис занят'], [503, 'model_not_ready', 'Модель пока не готова'], [503, 'service_unavailable', 'временно недоступен']] as const)('distinct safe outcome %s/%s', (status, code, title) => {
  render(<ErrorPanel error={new ApiError(code, status)} />); expect(screen.getByRole('alert').textContent).toContain(title);
});
test('generic exceptions do not expose raw paths/secrets and retry is keyboard accessible', async () => {
  const retry = vi.fn(); render(<ErrorPanel error={new Error('private-secret C:/private/path')} onRetry={retry} />);
  expect(screen.getByRole('alert').textContent).not.toContain('private'); const user = userEvent.setup(); await user.tab(); expect(document.activeElement).toBe(screen.getByRole('button')); await user.keyboard('{Enter}'); expect(retry).toHaveBeenCalledOnce();
});
test('abort and unknown upload outcome do not claim cancellation or retry POST automatically', () => {
  const view = render(<ErrorPanel error={new DOMException('private', 'AbortError')} />); expect(screen.getByRole('alert').textContent).toContain('не отменено');
  view.rerender(<ErrorPanel error={new ApiError('upload_outcome_unknown')} />); expect(screen.getByRole('alert').textContent).toContain('перед повторной загрузкой'); expect(screen.queryByRole('button')).toBeNull();
});
