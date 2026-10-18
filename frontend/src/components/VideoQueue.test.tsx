import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { VideoQueue } from './VideoQueue';
import { ResultsOverview } from './ResultsOverview';
import type { QueueItem } from '../useVideoQueue';
import type { Diagnostics } from '../api/types';
import { fixtureCase } from '../fixtures/contract-fixtures';
afterEach(cleanup);
const item: QueueItem = { id: 'one', name: 'clip.mp4', size: 1024, state: 'uploading' };
const props = { items: [item], active: item, running: true, started: true, canStart: true, connectionLost: false, onStart: vi.fn(), onPause: vi.fn(), onAbort: vi.fn(), onRemove: vi.fn(), onClear: vi.fn(), onSettings: vi.fn() };
test('unknown upload progress is indeterminate and clearing cannot lose an active upload', () => {
  render(<VideoQueue {...props} progress={{ loaded: 0, total: 1024, computable: false }} />);
  expect(screen.getByRole('progressbar', { name: 'Загрузка clip.mp4' }).hasAttribute('value')).toBe(false);
  expect((screen.getByRole('button', { name: 'Очистить очередь' }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.queryByRole('button', { name: /Удалить clip/ })).toBeNull();
  expect(screen.getByText(/Не закрывайте вкладку/)).toBeTruthy(); expect(screen.queryByText(/100%/)).toBeNull();
});
test('only the current job supplies measured analysis progress; an accepted job alone needs no keep-tab warning', () => {
  const active = { ...item, state: 'processing' as const, jobId: '00000000-0000-4000-8000-000000000001' };
  const diagnostics = fixtureCase('ui_diagnostics') as Diagnostics;
  diagnostics.public = { job_id: active.jobId, status: 'processing' }; diagnostics.stage = 'inference'; diagnostics.duration_sec = 10; diagnostics.processed_sec = 4;
  const view = render(<VideoQueue {...props} items={[active]} active={active} diagnostics={{ ...diagnostics, job_id: 'foreign' }} />);
  expect(screen.getByRole('progressbar', { name: 'Анализ clip.mp4' }).hasAttribute('value')).toBe(false);
  view.rerender(<VideoQueue {...props} items={[active]} active={active} diagnostics={diagnostics} />);
  expect(screen.getByRole('progressbar', { name: 'Анализ clip.mp4' }).getAttribute('value')).toBe('4');
  expect(screen.queryByText(/Не закрывайте вкладку/)).toBeNull();
});
test('completed files leave the queue while pending files remain deletable', () => {
  const done: QueueItem = { ...item, state: 'done', events: 2, jobId: 'accepted', durationSec: 12.3 };
  const second: QueueItem = { ...item, id: 'two', name: 'second.mov', state: 'waiting' };
  render(<VideoQueue {...props} items={[done, second]} active={undefined} running={false} started={false} />);
  const rows = within(screen.getByRole('list', { name: 'Видео в очереди' })).getAllByRole('listitem');
  expect(rows).toHaveLength(1); expect(rows[0].textContent).toContain('second.mov');
  expect(screen.queryByText('clip.mp4')).toBeNull(); expect(rows[0].textContent).toContain('Длительность не определена');
  fireEvent.click(screen.getByRole('button', { name: 'Удалить second.mov из очереди' })); expect(props.onRemove).toHaveBeenCalledWith('two');
  expect(screen.getByRole('button', { name: 'Начать анализ · 1' })).toBeTruthy();
});
test('a fully completed queue is replaced by results with file details and a primary open action', () => {
  const done: QueueItem = { ...item, state: 'done', events: 1, jobId: 'accepted', durationSec: 12.3 };
  render(<><VideoQueue {...props} items={[done]} active={undefined} running={false} /><ResultsOverview items={[done]} onView={vi.fn()} onChooseFiles={vi.fn()} /></>);
  expect(screen.queryByRole('list', { name: 'Видео в очереди' })).toBeNull();
  expect(screen.getAllByText('clip.mp4')).toHaveLength(1); expect(screen.getByText('1 событие для проверки')).toBeTruthy();
  expect(screen.getByRole('listitem').textContent).toContain('00:12');
  expect(screen.getByRole('button', { name: 'Открыть результат clip.mp4' }).className).toContain('primary-button');
});
test('empty results, no detected events and a failed analysis remain distinct', () => {
  const view = render(<ResultsOverview items={[]} onView={vi.fn()} onChooseFiles={vi.fn()} />);
  expect(screen.getByText('Результаты появятся здесь после обработки видео')).toBeTruthy();
  view.rerender(<ResultsOverview items={[{ ...item, state: 'done', events: 0, jobId: 'ready' }, { ...item, id: 'failed', name: 'bad.mov', state: 'failed', message: 'Не удалось прочитать видео.' }]} onView={vi.fn()} onChooseFiles={vi.fn()} />);
  expect(screen.queryByText('Результаты появятся здесь после обработки видео')).toBeNull();
  expect(screen.getByText('Возможные нарушения не обнаружены')).toBeTruthy(); expect(screen.getByText('Ошибка анализа')).toBeTruthy();
  expect(screen.getByText('Не удалось прочитать видео.')).toBeTruthy(); expect(screen.getByRole('button', { name: 'Выбрать другое видео' })).toBeTruthy();
});
test('unknown event counts are not rendered as a clean result', () => {
  render(<ResultsOverview items={[{ ...item, state: 'done', jobId: 'ready' }]} onView={vi.fn()} onChooseFiles={vi.fn()} />);
  expect(screen.getByText('Количество событий не получено')).toBeTruthy(); expect(screen.queryByText('Возможные нарушения не обнаружены')).toBeNull();
});
test('lost polling can only request a state check, retaining the file row and job', () => {
  const active = { ...item, state: 'processing' as const, jobId: 'accepted' };
  render(<VideoQueue {...props} items={[active]} active={active} running={false} connectionLost />);
  expect(screen.getByRole('alert').textContent).toContain('Состояние задания сейчас неизвестно');
  fireEvent.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Проверить состояние' })); expect(props.onStart).toHaveBeenCalledOnce();
  expect(screen.getByRole('listitem').textContent).toContain('Обрабатывается');
});
