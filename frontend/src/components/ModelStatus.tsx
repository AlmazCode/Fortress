import { isModelReady, isPrototypeAvailable, type ModelStatusData } from '../api/types';
import { StatusBadge } from './ui';
export function ModelStatus({ model, pending, connected, fixtureMode = false, blocked = false, unavailable = false, onRefresh }: { model?: ModelStatusData; pending: boolean; connected: boolean; fixtureMode?: boolean; blocked?: boolean; unavailable?: boolean; onRefresh?: () => void }) {
  const ready = connected && !pending && !blocked && !unavailable && isModelReady(model) && !fixtureMode;
  const testOnly = fixtureMode || model?.test_only;
  const prototype = connected && !pending && !blocked && !unavailable && isPrototypeAvailable(model) && !fixtureMode;
  return <section className="model-panel" aria-labelledby="model-title">
    <div className="model-heading"><h2 id="model-title">Модель</h2><StatusBadge tone={ready ? 'success' : pending ? 'active' : 'neutral'} icon={ready ? 'check' : pending ? 'loader' : 'info'}>{pending ? 'Проверяем…' : unavailable || !connected ? 'Не проверена' : testOnly ? 'Тестовая' : prototype ? 'Прототип' : ready ? 'Готова' : 'Не готова'}</StatusBadge></div>
    {!pending && !unavailable && <p>{!connected ? 'Для проверки введите API-ключ.' : testOnly ? 'Тестовая модель. Найденные события требуют проверки сотрудником.' : prototype ? 'Обученная экспериментальная модель подключена. Анализ доступен для ручной проверки.' : ready ? 'Можно начать анализ.' : 'Для анализа нужна обученная модель.'}</p>}
    {connected && !pending && !unavailable && !ready && !prototype && !testOnly && <details><summary>Как подключить модель</summary><p>Администратор должен импортировать совместимую обученную модель по инструкции сервера.</p></details>}
    {connected && !ready && !prototype && !testOnly && onRefresh && <button className="text-button" disabled={pending} onClick={onRefresh}>Проверить готовность</button>}
    {model && !pending && !unavailable && (model.release_version || model.limitations.length > 0) && <details><summary>Сведения о модели</summary>{model.release_version && <p className="mono">Версия: {model.release_version}</p>}{model.limitations.map((line, index) => <p key={index} className="muted">{line}</p>)}</details>}
  </section>;
}
