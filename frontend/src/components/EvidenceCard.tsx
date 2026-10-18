import { useState } from 'react';
import { formatTime, type EvidenceFrame, type Finding, type Violation } from '../api/types';
import { StatusBadge } from './ui';
function evidenceData(frame: EvidenceFrame): string | undefined {
  if (frame.image_base64.length > 8388608 || !/^\/9j\/[A-Za-z0-9+/]*={0,2}$/.test(frame.image_base64)) return;
  try { const bytes = atob(frame.image_base64); if (bytes.length < 4 || bytes.charCodeAt(bytes.length - 2) !== 255 || bytes.charCodeAt(bytes.length - 1) !== 217) return; return `data:image/jpeg;base64,${frame.image_base64}`; } catch { return; }
}
function Frame({ frame, index, onSeek }: { frame: EvidenceFrame; index: number; onSeek: (time: number) => void }) {
  const [failed, setFailed] = useState(false); const src = evidenceData(frame);
  return <div className="evidence-frame">{src && !failed ? <button onClick={() => onSeek(frame.timestamp_sec)} aria-label={`Кадр ${index + 1}, исходное время ${frame.timestamp_sec} секунд`}><img src={src} onError={() => setFailed(true)} alt={`Исходный кадр ${index + 1} на ${formatTime(frame.timestamp_sec)}`} /><span>{frame.timestamp_sec} с</span></button> : <p className="field-error" role="alert">Кадр {index + 1} повреждён или недоступен.</p>}</div>;
}
export function EvidenceCard({ event, finding, onSeek, reviewOnly = false }: { event: Violation; finding?: Finding; onSeek: (time: number) => void; reviewOnly?: boolean }) {
  const url = finding?.source.url; const safeLink = url && /^https?:\/\//i.test(url) ? url : undefined;
  return <article className="evidence-card">
    <div className="event-heading"><StatusBadge tone={reviewOnly ? 'neutral' : 'warning'} icon={reviewOnly ? 'video' : 'alert'}>{reviewOnly ? 'Фрагмент для проверки' : 'Возможное нарушение'}</StatusBadge><button className="time-button" onClick={() => onSeek(event.timecode_sec)} aria-label={`Событие ${event.type}, ${event.timecode_sec} секунд`}>{formatTime(event.timecode_sec)} ↗</button></div>
    <h3>{event.type}</h3><p>{event.description}</p>
    {finding && <p className="muted">Исходный интервал: {finding.interval.start_sec}–{finding.interval.end_sec} с</p>}
    {event.evidence_frames.length < 1 || event.evidence_frames.length > 3 ? <p role="alert">Кадры события недоступны.</p> : <div className="evidence-grid">{event.evidence_frames.map((frame, index) => <Frame key={`${frame.timestamp_sec}-${frame.image_base64}-${index}`} frame={frame} index={index} onSeek={onSeek} />)}</div>}
    {finding && <details className="source-block"><summary>Источник и ограничения</summary><p>{safeLink ? <a href={safeLink} target="_blank" rel="noopener noreferrer">Открыть источник</a> : 'Ссылка не указана.'}</p><p className="muted">Редакция: {finding.source.revision ?? 'не указана'} · Раздел: {finding.source.section ?? 'не указан'}</p><p>{finding.source.verified ? 'Источник проверен. Применимость проверьте вручную.' : 'Источник не подтверждён.'}</p>{finding.source.limitations.map((line, i) => <p key={i}>{line}</p>)}</details>}
  </article>;
}
