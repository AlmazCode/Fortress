import { ApiError } from '../api/client';
export function describeError(error: unknown): { title: string; description: string } {
  if (error instanceof DOMException && error.name === 'AbortError') return { title: 'Запрос прерван', description: 'Принятое задание не отменено. Его можно открыть по ID.' };
  if (!(error instanceof ApiError)) return { title: 'Не удалось завершить запрос', description: 'Повторите проверку. Результат анализа не подтверждён.' };
  const byCode: Record<string, { title: string; description: string }> = {
    upload_outcome_unknown: { title: 'Приём файла не подтверждён', description: 'Сервер мог принять файл. Проверьте задание по ID перед повторной загрузкой.' },
    network: { title: 'Нет связи с сервисом', description: 'Проверьте соединение и повторите проверку.' },
    protocol: { title: 'Ответ сервиса не распознан', description: 'Повторите проверку. Если ошибка повторится, обратитесь к администратору.' },
    invalid_job_id: { title: 'Неверный ID задания', description: 'Введите UUID, полученный при приёме файла.' },
    invalid_preview: { title: 'Видео повреждено или недоступно', description: 'Не удалось загрузить видео для проверки событий.' },
    unsafe_media_url: { title: 'Ссылка на видео недействительна', description: 'Повторно откройте задание по ID.' },
  };
  if (byCode[error.code]) return byCode[error.code];
  const byStatus: Record<number, { title: string; description: string }> = {
    400: { title: 'Запрос или файл отклонён', description: 'Проверьте ID и ограничения видео.' },
    401: { title: 'Ключ не принят', description: 'Сбросьте ключ и введите действующий API-ключ.' },
    404: { title: 'Данные не найдены', description: 'Проверьте ID задания.' },
    413: { title: 'Превышен лимит размера', description: 'Максимальный размер видео — 200 МиБ.' },
    415: { title: 'Формат видео не поддерживается', description: 'Выберите MP4 или MOV с допустимыми параметрами.' },
    429: { title: 'Сервис занят', description: 'Попробуйте отправить файл позже.' },
    503: { title: error.code === 'model_not_ready' ? 'Модель пока не готова' : 'Сервис временно недоступен', description: error.code === 'model_not_ready' ? 'Обратитесь к администратору для подключения модели.' : 'Повторите проверку позже.' },
  };
  return byStatus[error.status ?? 0] ?? { title: 'Ошибка сервиса', description: 'Повторите проверку позже.' };
}
export function ErrorPanel({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = describeError(error);
  return <div className="error-panel" role="alert"><span className="error-symbol" aria-hidden="true">!</span><div><strong>{message.title}</strong><p>{message.description}</p>{onRetry && <button className="text-button" onClick={onRetry}>Повторить проверку</button>}</div></div>;
}
