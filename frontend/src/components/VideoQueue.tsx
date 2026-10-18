import { useLayoutEffect, useRef } from 'react';
import type { Diagnostics, UploadProgress } from '../api/types';
import type { QueueItem, QueueState } from '../useVideoQueue';
import { stageLabels } from './JobStatus';
import { isQueueFinished, useQueuePresence } from './useQueuePresence';

const labels: Record<QueueState, string> = {
  waiting: 'В очереди', uploading: 'Загрузка', processing: 'Анализ',
  done: 'Готово', failed: 'Ошибка', uncertain: 'Приём не подтверждён',
};
export function formatBytes(bytes: number): string {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} МиБ` : `${Math.max(1, Math.ceil(bytes / 1024))} КиБ`;
}
function QueueFile({ item, index }: { item: QueueItem; index: number }) {
  return <><span className="queue-number">{String(index).padStart(2, '0')}</span><strong className="queue-file-name" title={item.name}>{item.name}</strong><span className="queue-file-size">{item.size > 0 ? formatBytes(item.size) : 'Размер неизвестен'}</span></>;
}
export function VideoQueue({ items, active, running, started, canStart, blockedReason, progress, diagnostics, connectionLost, onStart, onPause, onAbort, onRemove, onClearWaiting, onView, onSettings }: {
  items: QueueItem[]; active?: QueueItem; running: boolean; started: boolean; canStart: boolean;
  blockedReason?: string; progress?: UploadProgress; diagnostics?: Diagnostics; connectionLost: boolean;
  onStart: () => void; onPause: () => void; onAbort: () => void; onRemove: (id: string) => void;
  onClearWaiting: () => void; onView: (id: string) => void; onSettings?: () => void;
}) {
  const { visible, finishExit } = useQueuePresence(items);
  const results = useRef(new Map<string, HTMLLIElement>());
  useLayoutEffect(() => {
    const focusedId = document.activeElement?.closest('[data-queue-id]')?.getAttribute('data-queue-id');
    if (focusedId && items.some(item => item.id === focusedId && isQueueFinished(item))) {
      results.current.get(focusedId)?.focus({ preventScroll: true });
    }
  }, [items]);
  if (!items.length) return null;
  const finished = items.filter(isQueueFinished);
  const waiting = items.filter(item => item.state === 'waiting').length;
  const done = items.filter(item => item.state === 'done').length;
  const failed = items.filter(item => item.state === 'failed').length;
  const errors = failed + items.filter(item => item.state === 'uncertain').length;
  const processed = diagnostics && diagnostics.job_id === active?.jobId && diagnostics.public.status === 'processing' ? diagnostics : undefined;
  const percent = progress?.computable && progress.total > 0 ? Math.min(100, Math.round(100 * progress.loaded / progress.total)) : undefined;
  return <section className="queue-panel" aria-labelledby="queue-title">
    <div className="queue-heading"><h2 id="queue-title">Очередь видео</h2><span className="queue-volume" role="status">{waiting || active ? `Готово ${done} из ${items.length}` : errors ? `Готово ${done}, ошибок ${errors}` : `Готово ${done} из ${items.length}`}</span></div>
    <div className="queue-controls">{running && (waiting > 0 || active) ? <button className="secondary-button" onClick={onPause}>Пауза</button> : (waiting > 0 || connectionLost) && <button className="primary-button" onClick={onStart} disabled={!canStart}>{connectionLost ? 'Восстановить связь' : started ? 'Продолжить' : 'Начать анализ'}</button>}{waiting > 0 && <button className="text-button" onClick={onClearWaiting}>Убрать ожидающие</button>}</div>
    {!canStart && blockedReason && <p className="queue-hint">{blockedReason}{onSettings && <button className="text-button queue-settings-link" onClick={onSettings}>Открыть настройки</button>}</p>}
    {visible.length > 0 ? <ol className="queue-list" aria-label="Видео в очереди" tabIndex={0}>{visible.map((item, index) => {
      const leaving = isQueueFinished(item);
      const position = leaving ? index + 1 : visible.slice(0, index + 1).filter(entry => !isQueueFinished(entry)).length;
      return <li key={item.id} data-queue-id={item.id} className={`queue-item queue-item-${item.state}${leaving ? ' queue-item-exiting' : ''}`} aria-label={`${item.name}, ${item.id === active?.id && connectionLost ? 'Связь прервана' : labels[item.state]}`} aria-hidden={leaving || undefined} inert={leaving || undefined} onTransitionEnd={event => { if (leaving && event.target === event.currentTarget && event.propertyName === 'flex-basis') finishExit(item.id); }}>
        {item.jobId ? <button className="queue-card" aria-label={`Открыть ${item.name}`} onClick={() => onView(item.jobId!)}><QueueFile item={item} index={position} /></button> : <div className="queue-card"><QueueFile item={item} index={position} /></div>}
      </li>;
    })}</ol> : <p className="queue-empty">Очередь пуста</p>}
    {active && <div className="queue-feedback">
      <strong>{active.name}</strong>
      {connectionLost ? <p className="queue-item-message">Связь прервана. Восстановите подключение для проверки состояния.</p> : active.state === 'uploading' ? <div className="queue-transfer"><span>Отправляем файл{percent === undefined ? '…' : ` · ${percent}%`}</span><progress aria-label={`Загрузка ${active.name}`} value={percent} max={100} /><button className="text-button" onClick={onAbort}>Прервать передачу</button></div> : <div className="queue-transfer"><span>{processed ? stageLabels[processed.stage] ?? 'Обрабатываем видео…' : 'Проверяем состояние…'}</span>{processed && processed.processed_sec !== null && processed.duration_sec > 0 ? <><progress aria-label={`Анализ ${active.name}`} value={Math.min(processed.processed_sec, processed.duration_sec)} max={processed.duration_sec} /><span>Обработано {processed.processed_sec.toLocaleString('ru-RU', { maximumFractionDigits: 1 })} из {processed.duration_sec.toLocaleString('ru-RU', { maximumFractionDigits: 1 })} с видео</span></> : <progress aria-label={`Анализ ${active.name}`} max={100} />}</div>}
    </div>}
    {items.filter(item => item.message).map(item => <div className="queue-item-message" key={item.id}>{item.name}: {item.message}{item.state === 'uncertain' && <button className="text-button" onClick={() => onRemove(item.id)}>Убрать из очереди</button>}</div>)}
    {(waiting > 0 || active) && <p className="queue-hint">{active ? 'Пауза не отменяет принятое сервером задание.' : 'Файлы будут обработаны по очереди. Не закрывайте вкладку.'}</p>}
    {finished.length > 0 && <section className="queue-history" aria-label="Завершённые видео"><div className="queue-history-heading"><h3>Завершённые · {finished.length}</h3><button className="text-button" onClick={() => finished.forEach(item => onRemove(item.id))}>Очистить завершённые</button></div><ul className="queue-results">{finished.map(item => <li key={item.id} className={`queue-item-${item.state}`} aria-label={`${item.name}, ${labels[item.state]}`} tabIndex={-1} ref={element => { if (element) results.current.set(item.id, element); else results.current.delete(item.id); }}>
      {item.jobId ? <button className="queue-card" aria-label={`Открыть ${item.name}`} onClick={() => onView(item.jobId!)}><QueueFile item={item} index={items.findIndex(entry => entry.id === item.id) + 1} /></button> : <div className="queue-card"><QueueFile item={item} index={items.findIndex(entry => entry.id === item.id) + 1} /></div>}
    </li>)}</ul></section>}
  </section>;
}
