import { formatTime, type Diagnostics, type Finding, type Job } from '../api/types';

export function findingLabel(finding: Finding) {
  return finding.support === 'unsupported' ? 'Не поддерживается' : finding.status === 'unknown' ? 'Недостаточно данных' : finding.status === 'triggered' ? 'Возможное нарушение' : 'Не сработало';
}

export interface Playback { time: number; duration: number }
export function VideoTimeline({ job, diagnostics, playback, selectedTime, onSeek }: {
  job: Extract<Job, { status: 'done' }>; diagnostics?: Diagnostics; playback?: Playback;
  selectedTime?: number; onSeek: (time: number) => void;
}) {
  const matching = diagnostics?.job_id === job.job_id ? diagnostics : undefined;
  const duration = playback && Number.isFinite(playback.duration) && playback.duration > 0 ? playback.duration : matching?.duration_sec ?? 0;
  const scaled = Number.isFinite(duration) && duration > 0;
  const validTime = (time: number) => Number.isFinite(time) && time >= 0 && (!scaled || time <= duration);
  const findings = matching?.timeline?.findings ?? [];
  const triggered = findings.filter(finding => finding.status === 'triggered');
  const other = findings.filter(finding => finding.status !== 'triggered');
  const current = playback?.time ?? selectedTime ?? 0;
  const position = scaled && validTime(current) ? current / duration * 100 : 0;
  const tick = (time: number) => duration < 5 ? `${time.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} с` : formatTime(time);
  function ruleLane(finding: Finding, index: number) {
    const { start_sec: start, end_sec: end } = finding.interval;
    const valid = validTime(start) && validTime(end) && end >= start;
    return <div className="timeline-lane" key={index}><span className="timeline-lane-label" title={finding.rule_id}>{finding.rule_id}</span><div className="timeline-track">
      {valid ? <button className={`timeline-interval ${finding.status === 'triggered' && finding.support === 'supported' ? 'triggered' : finding.status === 'not_triggered' ? 'clear' : 'unknown'} ${selectedTime === start ? 'selected' : ''}`} style={{ left: `${start / duration * 100}%`, width: `${(end - start) / duration * 100}%` }} aria-label={`Правило ${finding.rule_id}: ${start}–${end} секунд, ${findingLabel(finding)}`} title={`${finding.rule_id} · ${start}–${end} с · ${findingLabel(finding)}`} onClick={() => onSeek(start)}><span>{findingLabel(finding)}</span></button> : <span className="timeline-empty">Интервал за пределами видео</span>}
    </div></div>;
  }
  return <section className="timeline-panel" aria-labelledby="timeline-title">
    <div className="timeline-heading"><h3 id="timeline-title">Таймлайн видео</h3><span>{formatTime(validTime(current) ? current : 0)}{scaled && ` / ${formatTime(duration)}`}</span></div>
    {scaled ? <>
      <div className="timeline-axis"><div><label className="sr-only" htmlFor="video-timeline-position">Позиция в видео</label>
      <input id="video-timeline-position" className="timeline-scrubber" type="range" min={0} max={duration} step="any" value={validTime(current) ? current : 0} aria-valuetext={`${validTime(current) ? current : 0} секунд`} onChange={event => onSeek(Number(event.target.value))} />
      <div className="timeline-ruler" aria-hidden="true">{[0, .25, .5, .75, 1].map(fraction => <span key={fraction}>{tick(duration * fraction)}</span>)}</div></div></div>
      <div className="timeline-lane"><span className="timeline-lane-label">События</span><div className="timeline-track">
        <span className="timeline-playhead" style={{ left: `${position}%` }} aria-hidden="true" />
        {job.violations.map((event, index) => validTime(event.timecode_sec) && <button key={index} className={`timeline-marker ${selectedTime === event.timecode_sec ? 'selected' : ''}`} style={{ left: `${event.timecode_sec / duration * 100}%` }} aria-label={`Событие ${index + 1}: ${event.type}, ${event.timecode_sec} секунд`} aria-pressed={selectedTime === event.timecode_sec} title={`${event.timecode_sec} с · ${event.type}`} onClick={() => onSeek(event.timecode_sec)}>{index + 1}</button>)}
        {job.violations.length === 0 && <span className="timeline-empty">Событий не найдено</span>}
      </div></div>
      {triggered.map(ruleLane)}
      {other.length > 0 && <details className="timeline-other"><summary>Остальные проверки · {other.length}</summary>{other.map(ruleLane)}</details>}
    </> : <p className="muted">Длительность видео не получена. Переходите по таймкодам событий ниже.</p>}
    {job.violations.some(event => !validTime(event.timecode_sec)) && <p role="alert" className="field-error">Есть события с таймкодом за пределами видео.</p>}
    {(job.violations.length > 0 || findings.length > 0) && <p className="timeline-hint">Нажмите метку или интервал для перехода к фрагменту. Основания правил приведены ниже.</p>}
  </section>;
}
