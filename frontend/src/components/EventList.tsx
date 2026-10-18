import type { Diagnostics, Job, RuleSource } from '../api/types';
import { EvidenceCard } from './EvidenceCard';
const sourceKinds: Record<RuleSource['source_kind'], string> = {
  official: 'Официальный документ', internal_policy: 'Внутренний регламент',
  synthetic: 'Тестовый источник', unverified: 'Непроверенный источник',
};
const versionNames: Record<keyof Diagnostics['versions'], string> = {
  dataset: 'Данные', annotations: 'Разметка', split: 'Выборка', rules: 'Правила',
  model: 'Модель', preprocessing: 'Подготовка видео', taxonomy: 'Классы событий',
};
export function EventList({ job, diagnostics, onSeek }: { job: Extract<Job, { status: 'done' }>; diagnostics?: Diagnostics; onSeek: (time: number) => void }) {
  const matching = diagnostics?.job_id === job.job_id ? diagnostics : undefined;
  return <section className="results-panel" aria-labelledby="results-title">
    <h2 id="results-title">{job.violations.length ? `События для проверки · ${job.violations.length}` : 'События не найдены'}</h2>
    <p className="result-note">Проверьте результат по исходному видео. Анализ учитывает только доступные данные и поддерживаемые правила.</p>
    {matching?.provenance.kind === 'synthetic' && <p className="fixture-banner">Демонстрационный результат: искусственные данные.</p>}
    <div className="event-list">{job.violations.map((event, index) => <EvidenceCard key={`${job.job_id}-${event.type}-${event.timecode_sec}-${index}`} event={event} onSeek={onSeek} />)}</div>
    <section className="coverage-panel" aria-label="Покрытие и ограничения"><h3>Покрытие и ограничения</h3>
      {!matching ? <p>Расширенные сведения не получены. Источники и полнота анализа не подтверждены.</p> : <>
        <p>Покрытие: {matching.coverage === 'full' ? 'полное по поддерживаемым условиям' : matching.coverage === 'partial' ? 'частичное' : 'недостаточное'}.</p>
        {(matching.unknown.length > 0 || matching.unsupported.length > 0) && <p>Не все условия и правила удалось проверить.</p>}
        {matching.limitations.map((line, index) => <p key={index}>{line}</p>)}
        <details><summary>Подробности анализа</summary>
          {matching.unknown.length > 0 && <p>Неизвестные условия: {matching.unknown.join(', ')}.</p>}
          {matching.unsupported.length > 0 && <p>Неподдерживаемые правила: {matching.unsupported.join(', ')}.</p>}
          {matching.timeline?.findings.map((finding, index) => <article className="coverage-item" key={index}>
            <h4>{finding.rule_id}</h4><span className="pill neutral">{finding.support === 'unsupported' ? 'Не поддерживается' : finding.status === 'unknown' ? 'Недостаточно данных' : finding.status === 'triggered' ? 'Срабатывание' : 'Не сработало'}</span>
            <p>{finding.interval.start_sec}–{finding.interval.end_sec} с · {finding.reason}</p>
            <p>{sourceKinds[finding.source.source_kind]} · редакция {finding.source.revision ?? 'не указана'} · раздел {finding.source.section ?? 'не указан'}.</p>
            <p>{finding.source.verified ? 'Источник проверен.' : 'Источник не подтверждён.'}</p>
            {finding.source.url && (/^https?:\/\//i.test(finding.source.url) ? <a href={finding.source.url} target="_blank" rel="noopener noreferrer">Открыть источник</a> : <p>Ссылка на источник недействительна.</p>)}
            {finding.source.limitations.map((line, i) => <p key={i}>{line}</p>)}
          </article>)}
          <dl className="versions">{Object.entries(matching.versions).map(([name, value]) => <div key={name}><dt>{versionNames[name as keyof typeof versionNames]}</dt><dd>{value ?? 'не указана'}</dd></div>)}</dl>
          <p className="muted">Связь событий с конкретными правилами не указана.</p>
          {matching.provenance.kind === 'synthetic' && <p className="mono">Тестовый источник: {matching.provenance.source_id}</p>}
        </details>
      </>}
    </section>
  </section>;
}
