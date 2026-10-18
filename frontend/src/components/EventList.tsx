import { formatTime, type Diagnostics, type Finding, type Job } from '../api/types';
import { EvidenceCard } from './EvidenceCard';
import { RuleSource } from './RuleSource';
import { findingLabel } from './VideoTimeline';
const versionNames: Record<keyof Diagnostics['versions'], string> = {
  dataset: 'Данные', annotations: 'Разметка', split: 'Выборка', rules: 'Правила',
  model: 'Модель', preprocessing: 'Подготовка видео', taxonomy: 'Классы событий',
};
export function EventList({ job, diagnostics, onSeek }: { job: Extract<Job, { status: 'done' }>; diagnostics?: Diagnostics; onSeek: (time: number) => void }) {
  const matching = diagnostics?.job_id === job.job_id ? diagnostics : undefined;
  const findings = matching?.timeline?.findings ?? [];
  const triggered = findings.filter(finding => finding.status === 'triggered');
  const other = findings.filter(finding => finding.status !== 'triggered');
  function ruleCard(finding: Finding, index: number) {
    const { start_sec: start, end_sec: end } = finding.interval;
    const valid = Number.isFinite(start) && Number.isFinite(end) && start >= 0 && end >= start && !!matching && end <= matching.duration_sec;
    return <article className="rule-card" key={index}>
      <div className="event-heading"><h4>Правило {finding.rule_id}</h4><span className={`pill ${finding.status === 'triggered' && finding.support === 'supported' ? 'warning' : 'neutral'}`}>{findingLabel(finding)}</span></div>
      <button className="time-button" disabled={!valid} onClick={() => onSeek(start)} aria-label={`Интервал правила ${finding.rule_id}, ${start}–${end} секунд`}>{formatTime(start)}–{formatTime(end)} ↗</button>
      {!valid && <p className="field-error">Интервал за пределами видео.</p>}
      <p className="rule-reason">{finding.reason}</p>
      <RuleSource source={finding.source} />
    </article>;
  }
  return <section className="results-panel" aria-labelledby="results-title">
    <h2 id="results-title">{job.violations.length ? `События для проверки · ${job.violations.length}` : 'События не найдены'}</h2>
    <p className="result-note">Проверьте результат по исходному видео. Анализ учитывает только доступные данные и поддерживаемые правила.</p>
    {matching?.provenance.kind === 'synthetic' && <p className="fixture-banner">Демонстрационный результат: искусственные данные.</p>}
    <div className="event-list">{job.violations.map((event, index) => <EvidenceCard key={`${job.job_id}-${event.type}-${event.timecode_sec}-${index}`} event={event} onSeek={onSeek} />)}</div>
    <section className="rule-results" aria-label="Правила и нормативные основания">
      <h3>Правила и нормативные основания</h3>
      {findings.length ? <>
        {job.violations.length > 0 && <p className="muted">Основания относятся к интервалам правил. Связь событий с конкретными правилами не указана.</p>}
        {triggered.length > 0 ? <div className="rule-list">{triggered.map(ruleCard)}</div> : <p className="muted">Подтверждённое нормативное основание для найденных событий не предоставлено.</p>}
        {other.length > 0 && <details className="other-rule-results"><summary>Остальные правила и ограничения · {other.length}</summary><div className="rule-list">{other.map(ruleCard)}</div></details>}
      </> : <p className="muted">Нормативное основание не предоставлено.</p>}
    </section>
    <section className="coverage-panel" aria-label="Покрытие и ограничения"><h3>Покрытие и ограничения</h3>
      {!matching ? <p>Расширенные сведения не получены. Источники и полнота анализа не подтверждены.</p> : <>
        <p>Покрытие: {matching.coverage === 'full' ? 'полное по поддерживаемым условиям' : matching.coverage === 'partial' ? 'частичное' : 'недостаточное'}.</p>
        {(matching.unknown.length > 0 || matching.unsupported.length > 0) && <p>Не все условия и правила удалось проверить.</p>}
        {matching.limitations.map((line, index) => <p key={index}>{line}</p>)}
        <details><summary>Подробности анализа</summary>
          {matching.unknown.length > 0 && <p>Неизвестные условия: {matching.unknown.join(', ')}.</p>}
          {matching.unsupported.length > 0 && <p>Неподдерживаемые правила: {matching.unsupported.join(', ')}.</p>}
          <dl className="versions">{Object.entries(matching.versions).map(([name, value]) => <div key={name}><dt>{versionNames[name as keyof typeof versionNames]}</dt><dd>{value ?? 'не указана'}</dd></div>)}</dl>
          {matching.provenance.kind === 'synthetic' && <p className="mono">Тестовый источник: {matching.provenance.source_id}</p>}
        </details>
      </>}
    </section>
  </section>;
}
