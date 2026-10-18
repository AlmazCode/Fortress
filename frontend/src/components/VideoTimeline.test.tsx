import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { VideoTimeline } from './VideoTimeline';
import { EventList } from './EventList';
import { fixtureCase } from '../fixtures/contract-fixtures';
import type { Diagnostics, Job } from '../api/types';

afterEach(cleanup);
function data() {
  const job = fixtureCase('violation') as Extract<Job, { status: 'done' }>;
  job.violations[0].timecode_sec = 2.173;
  const diagnostics = fixtureCase('ui_diagnostics') as Diagnostics;
  diagnostics.duration_sec = 10; diagnostics.public = job;
  const finding = diagnostics.timeline!.findings[0];
  finding.interval = { ...finding.interval, start_sec: 1.125, end_sec: 4.625 };
  return { job, diagnostics, finding };
}

test('event markers, rule intervals and the scrubber seek exact source seconds', () => {
  const { job, diagnostics } = data(), onSeek = vi.fn();
  render(<VideoTimeline job={job} diagnostics={diagnostics} onSeek={onSeek} selectedTime={2.173} />);
  const marker = screen.getByRole('button', { name: /Событие 1:/ });
  expect(marker.getAttribute('aria-pressed')).toBe('true'); fireEvent.click(marker);
  expect(onSeek).toHaveBeenLastCalledWith(2.173);
  fireEvent.click(screen.getByText(/Остальные проверки/));
  fireEvent.click(screen.getByRole('button', { name: /Правило synthetic_rule:/ }));
  expect(onSeek).toHaveBeenLastCalledWith(1.125);
  fireEvent.change(screen.getByRole('slider'), { target: { value: '7.375' } });
  expect(onSeek).toHaveBeenLastCalledWith(7.375);
  expect(screen.queryByText('Возможное нарушение')).toBeNull();
});

test('playback uses the actual decoded duration, and times outside it cannot be sought from the timeline', () => {
  const { job, diagnostics, finding } = data();
  job.violations[0].timecode_sec = 12; finding.interval.end_sec = 11;
  render(<VideoTimeline job={job} diagnostics={diagnostics} playback={{ time: 3.25, duration: 8 }} onSeek={vi.fn()} />);
  expect(screen.getByRole('slider').getAttribute('max')).toBe('8');
  expect(screen.getByRole('slider').getAttribute('value')).toBe('3.25');
  expect(screen.queryByRole('button', { name: /Событие 1:/ })).toBeNull();
  fireEvent.click(screen.getByText(/Остальные проверки/));
  expect(screen.queryByRole('button', { name: /Правило synthetic_rule:/ })).toBeNull();
  expect(screen.getByRole('alert').textContent).toContain('за пределами');
});

test('foreign job rules and duration never populate the selected video timeline', () => {
  const { job, diagnostics } = data(); diagnostics.job_id = 'another-job';
  render(<VideoTimeline job={job} diagnostics={diagnostics} onSeek={vi.fn()} />);
  expect(screen.queryByRole('slider')).toBeNull();
  expect(screen.queryByText('synthetic_rule')).toBeNull();
  expect(screen.getByText(/Длительность видео не получена/)).toBeTruthy();
});

test('legal reference fields remain attached to their own rule interval, without assigning them to an unrelated event', () => {
  const { job, diagnostics, finding } = data(), onSeek = vi.fn();
  finding.status = 'triggered'; finding.support = 'supported';
  finding.source = { ...finding.source, source_kind: 'official', url: 'https://example.org/source', section: 'Тестовый пункт 42', revision: 'test-revision', verified: true };
  const { container } = render(<EventList job={job} diagnostics={diagnostics} onSeek={onSeek} />);
  const rule = screen.getByRole('region', { name: 'Правила и нормативные основания' });
  expect(rule.textContent).toContain('Тестовый пункт 42'); expect(rule.textContent).toContain('test-revision');
  expect(screen.getByRole('link', { name: /Открыть документ/ }).getAttribute('href')).toBe(finding.source.url);
  expect(container.querySelector('.evidence-card')?.querySelector('.rule-source')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: /Интервал правила/ })); expect(onSeek).toHaveBeenCalledExactlyOnceWith(1.125);
});

test('unverified references and missing legal grounds are explicit and unsafe links are not opened', () => {
  const { job, diagnostics, finding } = data(); finding.source.url = 'javascript:alert(1)';
  const view = render(<EventList job={job} diagnostics={diagnostics} onSeek={vi.fn()} />);
  expect(screen.queryByRole('link')).toBeNull(); expect(screen.getByText(/юридический вывод не установлен/)).toBeTruthy();
  expect(screen.getByText('Название документа не предоставлено.')).toBeTruthy();
  view.rerender(<EventList job={job} onSeek={vi.fn()} />);
  expect(screen.getByText('Нормативное основание не предоставлено.')).toBeTruthy();
  expect(screen.queryByText('Тестовый пункт 42')).toBeNull();
});
