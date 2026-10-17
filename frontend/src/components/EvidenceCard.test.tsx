import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { Diagnostics, Job } from '../api/types';
import { fixtureCase } from '../fixtures/contract-fixtures';
import { EvidenceCard } from './EvidenceCard';
import { EventList } from './EventList';
const done = () => fixtureCase('violation') as Extract<Job, { status: 'done' }>;
afterEach(cleanup);
test.each([1, 2, 3])('shows %s original JPEG frames and seeks the clicked source timestamp', count => {
  const event = done().violations[0], onSeek = vi.fn(); event.evidence_frames = Array.from({ length: count }, (_, i) => ({ ...event.evidence_frames[0], timestamp_sec: 1.173 + i }));
  render(<EvidenceCard event={event} onSeek={onSeek} />); expect(screen.getAllByRole('img')).toHaveLength(count);
  fireEvent.click(screen.getByRole('button', { name: /Кадр 1,/ })); expect(onSeek).toHaveBeenCalledExactlyOnceWith(1.173);
});
test('invalid base64 and browser JPEG errors are visible', () => {
  const event = done().violations[0]; const view = render(<EvidenceCard event={event} onSeek={vi.fn()} />);
  fireEvent.error(screen.getByRole('img')); expect(screen.getByRole('alert').textContent).toContain('повреждён');
  event.evidence_frames[0].image_base64 = 'not-jpeg'; view.rerender(<EvidenceCard event={event} onSeek={vi.fn()} />); expect(screen.queryByRole('img')).toBeNull();
});
test('source interval, revision and limitations use actual finding fields; unsafe links are suppressed', () => {
  const d = fixtureCase('ui_diagnostics') as Diagnostics; const finding = d.timeline!.findings[0]; finding.source.url = 'javascript:alert(1)'; finding.source.revision = 'rev-test'; finding.source.limitations = ['Unverified fixture source'];
  render(<EvidenceCard event={done().violations[0]} finding={finding} onSeek={vi.fn()} />);
  expect(screen.getByText(/Исходный интервал/).textContent).toContain(String(finding.interval.end_sec)); expect(screen.getByText(/Редакция/).textContent).toContain('rev-test'); expect(screen.getByText('Unverified fixture source')).toBeTruthy(); expect(screen.queryByRole('link')).toBeNull();
});
test('unknown/unsupported and versions remain visible; sources are not assigned to events by list order', () => {
  const d = fixtureCase('ui_diagnostics') as Diagnostics;
  const { container } = render(<EventList job={done()} diagnostics={d} onSeek={vi.fn()} />);
  expect(screen.getByText(/Неизвестно:/).textContent).toContain('actor'); expect(screen.getByText(/SYNTHETIC TEST/)).toBeTruthy();
  expect(screen.getByText('Не поддерживается')).toBeTruthy(); expect(container.querySelector('.evidence-card')?.textContent).toContain('Связь с конкретным правилом не предоставлена');
  expect(screen.getByText(/не доказывает безопасность/)).toBeTruthy();
});
test('foreign-job diagnostics are not substituted and empty events do not promise safety', () => {
  const d = fixtureCase('ui_diagnostics') as Diagnostics; d.job_id = '00000000-0000-4000-8000-000000000002';
  render(<EventList job={fixtureCase('no_violation') as Extract<Job, { status: 'done' }>} diagnostics={d} onSeek={vi.fn()} />);
  expect(screen.getByText(/Расширенные сведения не получены/)).toBeTruthy(); expect(screen.queryByText(/SYNTHETIC TEST/)).toBeNull(); expect(screen.getByText(/не считаются проверенными/)).toBeTruthy();
});
