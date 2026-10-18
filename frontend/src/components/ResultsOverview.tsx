import type { QueueItem } from '../useVideoQueue';
import { VideoFile } from './VideoFile';
import { Button, Icon, StatusBadge } from './ui';

export function ResultsOverview({ items, onView, onChooseFiles }: { items: QueueItem[]; onView: (id: string) => void; onChooseFiles: () => void }) {
  const finished = items.filter(item => item.state === 'done' || item.state === 'failed');
  return <section className="results-overview" aria-labelledby="overview-title">
    <div className="section-heading"><h2 id="overview-title">Результаты анализа</h2>{finished.length > 0 && <span className="count-label">{finished.length}</span>}</div>
    {!finished.length ? <div className="empty-results"><span className="empty-symbol"><Icon name="video" /></span><p>Результаты появятся здесь после обработки видео</p></div> : <ul className="result-list">{finished.map(item => <li className={`result-row ${item.state === 'failed' ? 'result-row-error' : ''}`} key={item.id}>
      <VideoFile item={item} />
      <div className="result-summary">{item.state === 'failed' ? <><StatusBadge tone="danger" icon="alert">Ошибка анализа</StatusBadge><p>{item.message ?? 'Анализ не завершён. Выберите другое видео или проверьте настройки.'}</p></> : item.events === undefined ? <StatusBadge icon="info">Количество событий не получено</StatusBadge> : <StatusBadge tone={item.events > 0 ? 'warning' : 'success'} icon={item.events > 0 ? 'alert' : 'check'}>{item.events > 0 ? `Событий для проверки: ${item.events}` : 'Возможные нарушения не обнаружены'}</StatusBadge>}</div>
      {item.state === 'done' && item.jobId ? <Button id={`result-${item.id}`} icon="arrow" aria-label={`Посмотреть результат ${item.name}`} onClick={() => onView(item.jobId!)}>Посмотреть результат</Button> : <Button onClick={onChooseFiles}>Выбрать другое видео</Button>}
    </li>)}</ul>}
  </section>;
}
