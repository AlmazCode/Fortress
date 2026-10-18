import type { Diagnostics, UploadProgress } from '../api/types';
import type { QueueItem, QueueState } from '../useVideoQueue';
import { stageLabels } from './JobStatus';
import { VideoFile } from './VideoFile';
import { Button, Notification, StatusBadge, type IconName } from './ui';
export { formatBytes } from './VideoFile';
const statuses: Record<QueueState, { label: string; tone: 'neutral' | 'active' | 'success' | 'danger' | 'warning'; icon: IconName }> = {
  waiting: { label: 'В очереди', tone: 'neutral', icon: 'clock' },
  uploading: { label: 'Обрабатывается', tone: 'active', icon: 'loader' },
  processing: { label: 'Обрабатывается', tone: 'active', icon: 'loader' },
  done: { label: 'Готово', tone: 'success', icon: 'check' },
  failed: { label: 'Ошибка', tone: 'danger', icon: 'alert' },
  uncertain: { label: 'Приём не подтверждён', tone: 'warning', icon: 'alert' },
};
export function VideoQueue({ items, active, running, started, canStart, blockedReason, progress, diagnostics, connectionLost, onStart, onPause, onAbort, onRemove, onClear, onSettings }: {
  items: QueueItem[]; active?: QueueItem; running: boolean; started: boolean; canStart: boolean;
  blockedReason?: string; progress?: UploadProgress; diagnostics?: Diagnostics; connectionLost: boolean;
  onStart: () => void; onPause: () => void; onAbort: () => void; onRemove: (id: string) => void;
  onClear: () => void; onSettings?: () => void;
}) {
  if (!items.length) return null;
  const waiting = items.filter(item => item.state === 'waiting').length;
  const finished = items.filter(item => item.state === 'done' || item.state === 'failed').length;
  const detail = diagnostics?.job_id === active?.jobId && diagnostics?.public.status === 'processing' ? diagnostics : undefined;
  const percent = progress?.computable && progress.total > 0 ? Math.min(100, Math.round(100 * progress.loaded / progress.total)) : undefined;
  return <section className="queue-panel" aria-labelledby="queue-title">
    <div className="queue-heading"><div><h3 id="queue-title">Очередь видео <span className="count-label">{items.length}</span></h3><p role="status">Завершено {finished} из {items.length}</p></div>
      <div className="queue-controls">{running && (waiting > 0 || active) ? <Button icon="pause" onClick={onPause}>Пауза</Button> : (waiting > 0 || connectionLost) ? <Button variant="primary" icon="play" onClick={onStart} disabled={!canStart}>{connectionLost ? 'Проверить состояние' : started ? `Продолжить · ${waiting}` : `Начать анализ · ${waiting}`}</Button> : null}<Button variant="text" onClick={onClear} disabled={!!active || running}>Очистить очередь</Button></div>
    </div>
    {!canStart && waiting > 0 && blockedReason && <Notification tone="warning">{blockedReason}{onSettings && <Button variant="text" onClick={onSettings}>Открыть настройки</Button>}</Notification>}
    <ol className="queue-list" aria-label="Видео в очереди">{items.map(item => {
      const status = statuses[item.state];
      return <li className={`file-row file-row-${item.state}`} key={item.id} aria-label={`${item.name}, ${status.label}`}>
        <VideoFile item={item} />
        <StatusBadge tone={status.tone} icon={status.icon}>{status.label}</StatusBadge>
        <div className="file-row-action">{item.state === 'waiting' && <Button icon="trash" aria-label={`Удалить ${item.name} из очереди`} onClick={() => onRemove(item.id)} />}</div>
        {item.message && <p className="file-row-error">{item.message}</p>}
      </li>;
    })}</ol>
    {active && <div className="queue-processing" aria-label="Ход обработки">
      <div className="processing-heading"><div><span className="eyebrow">Текущий файл</span><strong>{active.name}</strong></div><span>Завершено {finished} из {items.length}</span></div>
      <progress aria-label="Завершение очереди" value={finished} max={items.length} />
      {connectionLost ? <Notification tone="danger" role="alert"><strong>Связь с сервисом прервана</strong><p>Состояние задания сейчас неизвестно. Повторная проверка не загружает файл заново.</p><Button onClick={onStart}>Проверить состояние</Button></Notification> : active.state === 'uploading' ? <div className="queue-transfer"><span>Загружаем файл{percent === undefined ? '…' : ` · ${percent}%`}</span><progress aria-label={`Загрузка ${active.name}`} value={percent} max={100} /><Button variant="text" onClick={onAbort}>Прервать передачу</Button></div> : <div className="queue-transfer"><span>{detail ? stageLabels[detail.stage] ?? 'Обрабатываем видео…' : 'Проверяем состояние…'}</span>{detail && detail.processed_sec !== null && detail.duration_sec > 0 ? <><progress aria-label={`Анализ ${active.name}`} value={Math.min(detail.processed_sec, detail.duration_sec)} max={detail.duration_sec} /><span>Обработано {detail.processed_sec.toLocaleString('ru-RU', { maximumFractionDigits: 1 })} из {detail.duration_sec.toLocaleString('ru-RU', { maximumFractionDigits: 1 })} с видео</span></> : <progress aria-label={`Анализ ${active.name}`} max={100} />}</div>}
      {(waiting > 0 || active.state === 'uploading') && <p className="helper-text">Не закрывайте вкладку, пока загружаются выбранные файлы.</p>}
      {!running && waiting > 0 && <p className="helper-text">Следующие загрузки на паузе. Принятое задание продолжает обрабатываться.</p>}
    </div>}
  </section>;
}