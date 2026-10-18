import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { VideoQueue } from './VideoQueue';
import type { QueueItem } from '../useVideoQueue';
import type { Diagnostics } from '../api/types';
import { fixtureCase } from '../fixtures/contract-fixtures';
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });
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

test('a finished card exits before the remaining queue shifts, while its result and keyboard focus are retained', () => {
  vi.useFakeTimers();
  const first: QueueItem = { ...item, state: 'processing', jobId: 'accepted' };
  const second: QueueItem = { ...item, id: 'two', name: 'second.mov', state: 'waiting' };
  const view = render(<VideoQueue {...props} items={[first, second]} active={first} />);
  screen.getByRole('button', { name: 'Открыть clip.mp4' }).focus();
  view.rerender(<VideoQueue {...props} items={[{ ...first, state: 'done' }, second]} active={undefined} />);
  const exiting = view.container.querySelector('[data-queue-id="one"]');
  expect(exiting?.getAttribute('aria-hidden')).toBe('true'); expect(exiting?.classList.contains('queue-item-exiting')).toBe(true);
  const history = screen.getByRole('region', { name: 'Завершённые видео' });
  expect(history.contains(document.activeElement)).toBe(true);
  fireEvent.click(within(history).getByRole('button', { name: 'Открыть clip.mp4' }));
  expect(props.onView).toHaveBeenCalledWith('accepted');
  act(() => { vi.advanceTimersByTime(650); });
  expect(view.container.querySelector('[data-queue-id="one"]')).toBeNull();
  expect(within(screen.getByRole('list', { name: 'Видео в очереди' })).getAllByRole('listitem')[0].textContent).toContain('second.mov');
});

test('rapid completions retire independently, without removing or reordering the next video', () => {
  vi.useFakeTimers();
  const second: QueueItem = { ...item, id: 'two', name: 'second.mov', state: 'waiting' };
  const third: QueueItem = { ...item, id: 'three', name: 'third.mp4', state: 'waiting' };
  const view = render(<VideoQueue {...props} items={[item, second, third]} />);
  const done = { ...item, state: 'done' as const };
  view.rerender(<VideoQueue {...props} items={[done, second, third]} active={undefined} />);
  act(() => { vi.advanceTimersByTime(300); });
  view.rerender(<VideoQueue {...props} items={[done, { ...second, state: 'failed' }, third]} active={undefined} />);
  act(() => { vi.advanceTimersByTime(350); });
  expect(view.container.querySelector('[data-queue-id="one"]')).toBeNull();
  expect(view.container.querySelector('[data-queue-id="two"]')).not.toBeNull();
  act(() => { vi.advanceTimersByTime(300); });
  expect(view.container.querySelector('[data-queue-id="two"]')).toBeNull();
  expect(view.container.querySelector('[data-queue-id="three"]')?.textContent).toContain('В очереди · 1');
  expect(within(screen.getByRole('region', { name: 'Завершённые видео' })).getAllByRole('listitem')).toHaveLength(2);
});

test('reduced motion removes the finished tile immediately', () => {
  vi.useFakeTimers();
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  const second: QueueItem = { ...item, id: 'two', name: 'second.mov', state: 'waiting' };
  const view = render(<VideoQueue {...props} items={[item, second]} />);
  view.rerender(<VideoQueue {...props} items={[{ ...item, state: 'done' }, second]} active={undefined} />);
  expect(view.container.querySelector('[data-queue-id="one"]')).toBeNull();
  expect(screen.getByRole('region', { name: 'Завершённые видео' })).toBeTruthy();
  view.rerender(<VideoQueue {...props} items={[]} active={undefined} />);
  act(() => { vi.advanceTimersByTime(1000); });
  expect(screen.queryByRole('region', { name: 'Очередь видео' })).toBeNull();
});

test('reset during an exit cancels its timer and cannot remove a newly added card', () => {
  vi.useFakeTimers();
  const view = render(<VideoQueue {...props} />);
  view.rerender(<VideoQueue {...props} items={[{ ...item, state: 'done' }]} active={undefined} />);
  expect(view.container.querySelector('.queue-item-exiting')).not.toBeNull();
  view.rerender(<VideoQueue {...props} items={[]} active={undefined} />);
  view.rerender(<VideoQueue {...props} items={[{ ...item, state: 'waiting' }]} active={undefined} />);
  act(() => { vi.advanceTimersByTime(1000); });
  expect(view.container.querySelector('[data-queue-id="one"]')?.textContent).toContain('В очереди · 1');
});
