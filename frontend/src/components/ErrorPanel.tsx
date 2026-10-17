import { ApiError } from '../api/client';
export function describeError(error: unknown): { title: string; description: string } {
  if (error instanceof DOMException && error.name === 'AbortError') return { title: 'Просмотр запроса прерван', description: 'Принятое сервером задание не отменено. Его можно открыть по ID с API-ключом.' };
  if (!(error instanceof ApiError)) return { title: 'Не удалось завершить запрос', description: 'Повторите проверку. Результат анализа не подтверждён.' };
  const byCode: Record<string, { title: string; description: string }> = {
    upload_outcome_unknown: { title: 'Приём файла не подтверждён', description: 'Сервер мог принять файл. Не отправляйте его повторно автоматически. Вернитесь по известному ID или уточните состояние сервиса.' },
    network: { title: 'Нет связи с сервисом', description: 'Состояние задания неизвестно. Проверьте соединение и повторите GET, не загружая файл заново.' },
    protocol: { title: 'Ответ сервиса не распознан', description: 'Сервис прислал неожиданный ответ. Результат не подтверждён; демонстрационные данные не подставляются.' },
    invalid_job_id: { title: 'Неверный ID задания', description: 'Введите UUID, полученный при приёме файла.' },
    invalid_preview: { title: 'Видео повреждено или недоступно', description: 'Поддерживаемое защищённое видео не получено. Видеопроверка доказательств не выполнена.' },
    unsafe_media_url: { title: 'Маршрут видео отклонён', description: 'Для медиа требуется защищённый маршрут того же задания на этом сервисе.' },
  };
  if (byCode[error.code]) return byCode[error.code];
  const byStatus: Record<number, { title: string; description: string }> = {
    400: { title: 'Запрос или файл отклонён', description: 'Проверьте ID и ограничения видео.' },
    401: { title: 'Ключ не принят', description: 'Сбросьте ключ и введите действующий API-ключ.' },
    404: { title: 'Данные не найдены', description: 'Проверьте ID задания и доступность медиа. Другой ролик не подставляется.' },
    413: { title: 'Превышен лимит размера', description: 'Допустимый размер видео и preview — до 200 МиБ.' },
    415: { title: 'Формат видео не поддерживается', description: 'Выберите непустой MP4 или MOV. Сервер проверяет декодирование, длительность, разрешение и fps.' },
    429: { title: 'Сервис занят', description: 'Дождитесь освобождения сервиса. Новая отправка выполняется только вручную.' },
    503: { title: error.code === 'model_not_ready' ? 'Модель пока не готова' : 'Сервис временно недоступен', description: error.code === 'model_not_ready' ? 'Нужен совместимый обученный release. Откройте инструкцию локального импорта в панели модели.' : 'Повторите проверку позже. Готовность инфраструктуры не подтверждена.' },
  };
  return byStatus[error.status ?? 0] ?? { title: 'Ошибка сервиса', description: 'Запрос не завершён. Отсутствие ответа не означает отсутствие нарушений.' };
}
export function ErrorPanel({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = describeError(error);
  return <div className="error-panel" role="alert"><span className="error-symbol" aria-hidden="true">!</span><div><strong>{message.title}</strong><p>{message.description}</p>{onRetry && <button className="text-button" onClick={onRetry}>Повторить проверку</button>}</div></div>;
}
