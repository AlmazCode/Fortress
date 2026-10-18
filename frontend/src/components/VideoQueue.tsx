import type { Diagnostics, UploadProgress } from '../api/types';
import type { QueueItem, QueueState } from '../useVideoQueue';
import { stageLabels } from './JobStatus';

const labels: Record<QueueState, string> = {
  waiting: 'В очереди', uploading: 'Загрузка', processing: 'Анализ',
  done: 'Готово', failed: 'Ошибка', uncertain: 'Приём не подтверждён',
};
export function formatBytes(bytes: number): string {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} МиБ` : `${Math.max(1, Math.ceil(bytes / 1024))} КиБ`;
}
export function VideoQueue({ items, active, running, started, canStart, blockedReason, progress, diagnostics, connectionLost, onStart, onPause, onAbort, onRemove, onClearWaiting, onView }: {
  items: QueueItem[]; active?: QueueItem; running: boolean; started: boolean; canStart: boolean;
  blockedReason?: string; progress?: UploadProgress; diagnostics?: Diagnostics; connectionLost: boolean;
  onStart: () => void; onPause: () => void; onAbort: () => void; onRemove: (id: string) => void;
  onClearWaiting: () => void; onView: (id: string) => void;
}) {
  if (!items.length) return null;
  const waiting = items.filter(item => item.state === 'waiting').length;
  const done = items.filter(item => item.state === 'done').length;
  const failed = items.filter(item => item.state === 'failed').length;
  const errors = failed + items.filter(item => item.state === 'uncertain').length;
  const processed = diagnostics && diagnostics.job_id === active?.jobId && diagnostics.public.status === 'processing' ? diagnostics : undefined;
  const percent = progress?.computable && progress.total > 0 ? Math.min(100, Math.round(100 * progress.loaded / progress.total)) : undefined;
  return <section className="queue-panel" aria-labelledby="queue-title">
    <div className="queue-heading"><h2 id="queue-title">Очередь видео</h2><span className="queue-volume" role="status">{waiting || active ? `Готово ${done} из ${items.length}` : errors ? `Готово ${done}, ошибок ${errors}` : `Готово ${done} из ${items.length}`}</span></div>
    <div className="queue-controls">{running && (waiting > 0 || active) ? <button className="secondary-button" onClick={onPause}>Пауза</button> : (waiting > 0 || connectionLost) && <button className="primary-button" onClick={onStart} disabled={!canStart}>{connectionLost ? 'Восстановить связь' : started ? 'Продолжить' : 'Начать анализ'}</button>}{waiting > 1 && <button className="text-button" onClick={onClearWaiting}>Убрать ожидающие</button>}</div>
    {!canStart && blockedReason && <p className="queue-hint">{blockedReason}</p>}
    <ol className="queue-list">{items.map((item, index) => {
      const isActive = item.id === active?.id;
      const position = items.slice(0, index + 1).filter(entry => entry.state === 'waiting').length;
      const state = isActive && connectionLost ? 'Связь прервана' : item.state === 'waiting' ? `В очереди · ${position}` : labels[item.state];
      return <li key={item.id} className={`queue-item queue-item-${item.state}`}>
        <span className="queue-number" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
        <div className="queue-file"><strong title={item.name}>{item.name}</strong><div className="queue-meta">{item.size > 0 && <span>{formatBytes(item.size)}</span>}{item.state === 'done' && <span>Событий: {item.events ?? 0}</span>}</div>
          {item.message && <p className="queue-item-message">{item.message}</p>}
          {isActive && item.state === 'uploading' && <div className="queue-transfer"><span>Отправляем файл{percent === undefined ? '…' : ` · ${percent}%`}</span><progress aria-label={`Загрузка ${item.name}`} value={percent} max={100} /></div>}
          {isActive && item.state === 'processing' && !connectionLost && <div className="queue-transfer"><span>{processed ? stageLabels[processed.stage] ?? 'Обрабатываем видео…' : 'Проверяем состояние…'}</span>{processed && processed.processed_sec !== null && processed.duration_sec > 0 ? <><progress aria-label={`Анализ ${item.name}`} value={Math.min(processed.processed_sec, processed.duration_sec)} max={processed.duration_sec} /><span>Обработано {processed.processed_sec.toLocaleString('ru-RU', { maximumFractionDigits: 1 })} из {processed.duration_sec.toLocaleString('ru-RU', { maximumFractionDigits: 1 })} с видео</span></> : <progress aria-label={`Анализ ${item.name}`} max={100} />}</div>}
        </div>
        <div className="queue-item-actions"><span className={`pill ${item.state === 'done' ? 'success' : item.state === 'failed' || item.state === 'uncertain' || connectionLost && isActive ? 'queue-error' : 'neutral'}`}>{state}</span>
          {item.jobId && <button className="text-button" aria-label={`Открыть ${item.name}`} onClick={() => onView(item.jobId!)}>{item.state === 'done' ? 'Результат' : 'Открыть'}</button>}
          {item.state === 'uploading' && <button className="text-button" onClick={onAbort}>Прервать передачу</button>}
          {!isActive && <button className="queue-remove" onClick={() => onRemove(item.id)} aria-label={`Убрать ${item.name} из очереди`}>×</button>}
        </div>
      </li>;
    })}</ol>
    {(waiting > 0 || active) && <p className="queue-hint">{active ? 'Пауза не отменяет принятое сервером задание.' : 'Файлы будут обработаны по очереди. Не закрывайте вкладку.'}</p>}
  </section>;
}
