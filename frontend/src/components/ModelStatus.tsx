import { isModelReady, type ModelStatusData } from '../api/types';
export function ModelStatus({ model, pending, connected, fixtureMode = false, blocked = false, unavailable = false }: { model?: ModelStatusData; pending: boolean; connected: boolean; fixtureMode?: boolean; blocked?: boolean; unavailable?: boolean }) {
  const ready = connected && !pending && !blocked && !unavailable && isModelReady(model) && !fixtureMode;
  const testOnly = fixtureMode || model?.test_only;
  return <section className="model-panel" aria-labelledby="model-title">
    <div className="model-heading"><h2 id="model-title">Модель</h2><span className={`pill ${ready ? 'success' : 'neutral'}`}>{pending ? 'Проверяем…' : unavailable || !connected ? 'Не проверена' : testOnly ? 'Тестовая' : ready ? 'Готова' : 'Не готова'}</span></div>
    {!pending && !unavailable && <p>{!connected ? 'Для проверки введите API-ключ.' : testOnly ? 'Качество модели не проверено.' : ready ? 'Можно начать анализ.' : 'Для анализа нужна обученная модель.'}</p>}
    {connected && !pending && !unavailable && !ready && !testOnly && <details><summary>Как подключить модель</summary><p>Администратор должен импортировать совместимую обученную модель по инструкции сервера.</p></details>}
    {model && !pending && !unavailable && (model.release_version || model.limitations.length > 0) && <details><summary>Сведения о модели</summary>{model.release_version && <p className="mono">Версия: {model.release_version}</p>}{model.limitations.map((line, index) => <p key={index} className="muted">{line}</p>)}</details>}
  </section>;
}
