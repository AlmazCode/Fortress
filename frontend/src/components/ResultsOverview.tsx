import type { QueueItem } from '../useVideoQueue';
import { VideoFile } from './VideoFile';
import { Button, Icon, StatusBadge } from './ui';

function eventCount(count: number) {
  const last = count % 10, hundred = count % 100;
  const noun = last === 1 && hundred !== 11 ? 'событие' : last >= 2 && last <= 4 && (hundred < 12 || hundred > 14) ? 'события' : 'событий';
  return `${count} ${noun} для проверки`;
}
export function ResultsOverview({ items, onView, onChooseFiles, onClear, primaryAction = true }: { items: QueueItem[]; onView: (id: string) => void; onChooseFiles: () => void; onClear?: () => void; primaryAction?: boolean }) {
  const finished = items.filter(item => item.state === 'done' || item.state === 'failed');
  return <section className="results-overview" aria-labelledby="overview-title">
    <div className="section-heading"><h2 id="overview-title">Результаты анализа</h2>{finished.length > 0 && <><span className="count-label">{finished.length}</span>{onClear && <Button variant="text" onClick={onClear}>Очистить результаты</Button>}</>}</div>
    {!finished.length ? <div className="empty-results"><span className="empty-symbol"><Icon name="video" /></span><p>Результаты появятся здесь после обработки видео</p></div> : <ul className="result-list">{finished.map(item => <li className={`result-row ${item.state === 'failed' ? 'result-row-error' : ''}`} key={item.id}>
      <VideoFile item={item}><div className="result-summary">{item.state === 'failed' ? <><StatusBadge tone="danger" icon="alert">Ошибка анализа</StatusBadge><p>{item.message ?? 'Анализ не завершён. Выберите другое видео или проверьте настройки.'}</p></> : item.events === undefined ? <StatusBadge icon="info">Количество событий не получено</StatusBadge> : item.events > 0 ? <span className="result-event-count"><Icon name="alert" />{eventCount(item.events)}</span> : <StatusBadge tone="success" icon="check">Возможные нарушения не обнаружены</StatusBadge>}</div></VideoFile>
      {item.state === 'done' && item.jobId ? <Button variant={primaryAction ? 'primary' : 'secondary'} id={`result-${item.id}`} icon="arrow" aria-label={`Открыть результат ${item.name}`} onClick={() => onView(item.jobId!)}>Открыть результат</Button> : <Button onClick={onChooseFiles}>Выбрать другое видео</Button>}
    </li>)}</ul>}
  </section>;
}
