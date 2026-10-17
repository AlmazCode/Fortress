import { useState } from 'react';
import { formatTime, type EvidenceFrame, type Finding, type Violation } from '../api/types';
function evidenceData(frame: EvidenceFrame): string | undefined {
  if (frame.image_base64.length > 8388608 || !/^\/9j\/[A-Za-z0-9+/]*={0,2}$/.test(frame.image_base64)) return;
  try { const bytes = atob(frame.image_base64); if (bytes.length < 4 || bytes.charCodeAt(bytes.length - 2) !== 255 || bytes.charCodeAt(bytes.length - 1) !== 217) return; return `data:image/jpeg;base64,${frame.image_base64}`; } catch { return; }
}
function Frame({ frame, index, onSeek }: { frame: EvidenceFrame; index: number; onSeek: (time: number) => void }) {
  const [failed, setFailed] = useState(false); const src = evidenceData(frame);
  return <div className="evidence-frame">{src && !failed ? <button onClick={() => onSeek(frame.timestamp_sec)} aria-label={`Кадр ${index + 1}, исходное время ${frame.timestamp_sec} секунд`}><img src={src} onError={() => setFailed(true)} alt={`Исходный кадр ${index + 1} на ${formatTime(frame.timestamp_sec)}`} /><span>{frame.timestamp_sec} с</span></button> : <p className="field-error" role="alert">Кадр {index + 1} недоступен: повреждён JPEG/base64.</p>}</div>;
}
export function EvidenceCard({ event, finding, onSeek }: { event: Violation; finding?: Finding; onSeek: (time: number) => void }) {
  const url = finding?.source.url; const safeLink = url && /^https?:\/\//i.test(url) ? url : undefined;
  return <article className="evidence-card">
    <div className="event-heading"><span className="pill warning">Требует проверки</span><button className="time-button" onClick={() => onSeek(event.timecode_sec)} aria-label={`Событие ${event.type}, ${event.timecode_sec} секунд`}>{formatTime(event.timecode_sec)} ↗</button></div>
    <h3>{event.type}</h3><p>{event.description}</p>
    {finding && <p className="muted">Исходный интервал: {finding.interval.start_sec}–{finding.interval.end_sec} с</p>}
    {event.evidence_frames.length < 1 || event.evidence_frames.length > 3 ? <p role="alert">Неверное число доказательств: нужно 1–3 исходных JPEG.</p> : <div className="evidence-grid">{event.evidence_frames.map((frame, index) => <Frame key={`${frame.timestamp_sec}-${frame.image_base64}-${index}`} frame={frame} index={index} onSeek={onSeek} />)}</div>}
    <div className="source-block"><strong>Основание и ограничения</strong>{finding ? <><p>{safeLink ? <a href={safeLink} target="_blank" rel="noopener noreferrer">Источник ↗</a> : 'Проверяемая ссылка не предоставлена'}</p><p className="muted">Редакция: {finding.source.revision ?? 'не указана'} · Раздел: {finding.source.section ?? 'не указан'} · {finding.source.source_kind}</p><p>{finding.source.verified ? 'Источник отмечен как проверенный; применимость требует проверки оператором.' : 'Источник не подтверждён. Нормативная применимость не установлена.'}</p>{finding.source.limitations.map((line, i) => <p key={i}>{line}</p>)}</> : <p className="muted">Связь с конкретным правилом не предоставлена. Источник не приписывается событию по позиции в списке.</p>}</div>
  </article>;
}
