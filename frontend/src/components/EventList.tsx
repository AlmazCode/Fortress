import type { Diagnostics, Job } from '../api/types';
import { EvidenceCard } from './EvidenceCard';
export function EventList({ job, diagnostics, onSeek }: { job: Extract<Job, { status: 'done' }>; diagnostics?: Diagnostics; onSeek: (time: number) => void }) {
  const matching = diagnostics?.job_id === job.job_id ? diagnostics : undefined;
  return <section className="results-panel" aria-labelledby="results-title">
    <div className="section-header"><div><div className="section-eyebrow">03 / РЕЗУЛЬТАТЫ И ДОКАЗАТЕЛЬСТВА</div><h2 id="results-title">{job.violations.length ? `События для проверки · ${job.violations.length}` : 'Поддержанные проверки не нашли нарушений'}</h2></div><span className="pill neutral">Проверка оператором</span></div>
    <p className="result-note">Результат относится к наблюдаемым условиям и поддержанным правилам. Он не доказывает безопасность всех действий и не заменяет проверку видео.</p>
    {!job.violations.length && <div className="empty-result">Срабатываний нет. Неизвестные условия и неподдержанные правила не считаются проверенными.</div>}
    {matching?.provenance.kind === 'synthetic' && <p className="fixture-banner">SYNTHETIC TEST / DEMO · {matching.provenance.source_id}. Это искусственные данные.</p>}
    <div className="event-list">{job.violations.map((event, index) => <EvidenceCard key={`${job.job_id}-${event.type}-${event.timecode_sec}-${index}`} event={event} onSeek={onSeek} />)}</div>
    <section className="coverage-panel" aria-label="Покрытие и неизвестные условия"><h3>Покрытие и ограничения</h3>
      {!matching ? <p>Расширенные сведения не получены. Источники, версии, интервалы и полнота наблюдений не подтверждены.</p> : <>
        <p>Покрытие: {matching.coverage === 'full' ? 'полное по поддержанным условиям' : matching.coverage === 'partial' ? 'частичное' : 'недостаточное'}.</p>
        <p>Неизвестно: {matching.unknown.join(', ') || 'нет перечисленных условий'}. Не поддерживается: {matching.unsupported.join(', ') || 'нет перечисленных правил'}.</p>
        {matching.timeline?.findings.map((finding, index) => <article className="coverage-item" key={index}><h4>{finding.rule_id}</h4><span className="pill neutral">{finding.support === 'unsupported' ? 'Не поддерживается' : finding.status === 'unknown' ? 'Недостаточно данных' : finding.status === 'triggered' ? 'Срабатывание' : 'Не сработало'}</span><p>Интервал: {finding.interval.start_sec}–{finding.interval.end_sec} с · {finding.reason}</p><p>Источник: {finding.source.source_kind} · редакция {finding.source.revision ?? 'не указана'} · раздел {finding.source.section ?? 'не указан'}</p><p>{finding.source.verified ? 'Источник отмечен как проверенный.' : 'Источник не подтверждён.'}</p>{finding.source.url && (/^https?:\/\//i.test(finding.source.url) ? <a href={finding.source.url} target="_blank" rel="noopener noreferrer">Открыть источник</a> : <p>Ссылка на источник имеет неподдерживаемую схему.</p>)}{finding.source.limitations.map((line, i) => <p key={i}>{line}</p>)}</article>)}
        {matching.limitations.map((line, index) => <p key={index}>{line}</p>)}
        <dl className="versions">{Object.entries(matching.versions).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value ?? 'не предоставлена'}</dd></div>)}</dl>
        <p className="muted">K не задаёт идентификатор связи public violation → finding. Источники правил показаны отдельно; порядок не используется для атрибуции.</p>
      </>}
    </section>
  </section>;
}
