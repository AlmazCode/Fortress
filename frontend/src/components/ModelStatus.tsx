import { isModelReady, type ModelStatusData } from '../api/types';
export function ModelStatus({ model, pending, connected, fixtureMode = false, blocked = false }: { model?: ModelStatusData; pending: boolean; connected: boolean; fixtureMode?: boolean; blocked?: boolean }) {
  const ready = connected && !pending && !blocked && isModelReady(model) && !fixtureMode;
  return <section className="model-panel" aria-labelledby="model-title">
    <div className="model-heading"><div className="section-eyebrow">МОДЕЛЬ И ОКРУЖЕНИЕ</div><span className={`pill ${ready ? 'success' : 'neutral'}`}>{fixtureMode || model?.test_only ? 'Synthetic test / demo' : pending ? 'Проверяем' : ready ? 'Готова' : model ? 'model_not_ready' : 'Не проверена'}</span></div>
    <h2 id="model-title">{ready ? 'Можно начать анализ' : 'Готовность требует проверки'}</h2>
    <p>{!connected ? 'Введите API-ключ для проверки локального сервиса.' : pending ? 'Запрашиваем состояние локального сервиса.' : ready ? 'Сервис сообщил о готовности обученного и проверенного release. Выводы требуют проверки оператором.' : fixtureMode || model?.test_only ? 'Только синтетический тест интерфейса. Обученная модель и реальное качество не проверены.' : 'Без совместимого обученного release анализ недоступен: model_not_ready. Отсутствие результата не означает отсутствие нарушений.'}</p>
    {model?.release_version && <p className="mono">Release: {model.release_version}</p>}
    {model?.limitations.map((line, index) => <p key={index} className="muted">{line}</p>)}
    {connected && !ready && <details><summary>Как подготовить локальный release</summary><p>Администратор импортирует на локальный ПК сервиса обученный пакет: checkpoint, taxonomy, preprocessing, thresholds, версии и SHA-256 manifest. Перед импортом проверяет совместимость и валидацию. Точные команды публикуются в документации backend/ML; интерфейс не запускает обучение.</p></details>}
  </section>;
}
