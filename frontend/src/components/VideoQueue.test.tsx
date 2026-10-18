import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { VideoQueue } from './VideoQueue';
import type { QueueItem } from '../useVideoQueue';
import type { Diagnostics } from '../api/types';
import { fixtureCase } from '../fixtures/contract-fixtures';
afterEach(cleanup);
const item: QueueItem = { id: 'one', name: 'clip.mp4', size: 1024, state: 'uploading' };
const props = { items: [item], active: item, running: true, started: true, canStart: true, connectionLost: false, onStart: vi.fn(), onPause: vi.fn(), onAbort: vi.fn(), onRemove: vi.fn(), onClearWaiting: vi.fn(), onView: vi.fn() };
test('unknown upload progress stays indeterminate and an accepted job is never called cancelled', () => {
  render(<VideoQueue {...props} progress={{ loaded: 0, total: 1024, computable: false }} />);
  expect(screen.getByRole('progressbar', { name: 'Загрузка clip.mp4' }).hasAttribute('value')).toBe(false);
  expect(screen.getByText(/Пауза не отменяет принятое сервером задание/)).toBeTruthy();
  expect(screen.queryByText(/100%/)).toBeNull();
});
test('only the current job can supply measured analysis progress', () => {
  const active = { ...item, state: 'processing' as const, jobId: '00000000-0000-4000-8000-000000000001' };
  const diagnostics = fixtureCase('ui_diagnostics') as Diagnostics;
  diagnostics.public = { job_id: active.jobId, status: 'processing' }; diagnostics.stage = 'inference';
  diagnostics.duration_sec = 10; diagnostics.processed_sec = 4;
  const view = render(<VideoQueue {...props} items={[active]} active={active} diagnostics={{ ...diagnostics, job_id: '00000000-0000-4000-8000-000000000002' }} />);
  expect(screen.getByRole('progressbar', { name: 'Анализ clip.mp4' }).hasAttribute('value')).toBe(false);
  view.rerender(<VideoQueue {...props} items={[active]} active={active} diagnostics={diagnostics} />);
  expect(screen.getByRole('progressbar', { name: 'Анализ clip.mp4' }).getAttribute('value')).toBe('4');
  expect(screen.getByRole('progressbar', { name: 'Анализ clip.mp4' }).getAttribute('max')).toBe('10');
});

test('waiting files show their remaining queue position after an earlier file finishes', () => {
  const first: QueueItem = { ...item, state: 'done', jobId: 'accepted' };
  const second: QueueItem = { ...item, id: 'two', name: 'second.mov', state: 'waiting' };
  const third: QueueItem = { ...item, id: 'three', name: 'third.mp4', state: 'waiting' };
  render(<VideoQueue {...props} items={[first, second, third]} active={undefined} running={false} />);
  expect(screen.getByText('В очереди · 1').closest('li')?.textContent).toContain('second.mov');
  expect(screen.getByText('В очереди · 2').closest('li')?.textContent).toContain('third.mp4');
  fireEvent.click(screen.getByRole('button', { name: 'Открыть clip.mp4' })); expect(props.onView).toHaveBeenCalledWith('accepted');
});
