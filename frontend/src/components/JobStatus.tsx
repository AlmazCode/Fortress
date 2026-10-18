import { useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ApiClient, ApiError, validJobId } from '../api/client';
import type { FailureReason, Job } from '../api/types';

const reasons: Record<FailureReason, string> = {
  insufficient_evidence: 'Недостаточно данных для анализа.',
  deadline_exceeded: 'Превышен срок обработки.', decode_failed: 'Не удалось прочитать видео.',
  inference_failed: 'Модель не завершила обработку.', evidence_failed: 'Не удалось подготовить доказательства.',
  worker_lost: 'Обработка прервана.', internal_error: 'Ошибка обработки.', release_invalid: 'Модель несовместима или повреждена.',
};
const stages: Record<string, string> = {
  validation: 'Проверяем файл', queued: 'Ожидаем обработки', decoding: 'Читаем видео',
  inference: 'Анализируем видео', rules: 'Проверяем события', evidence: 'Подготавливаем кадры',
};
export function useJobPolling(client: ApiClient | undefined, id: string | undefined, pollMs = 1800) {
  return useQuery<Job>({
    queryKey: ['fortress', client?.session ?? 0, 'job', id ?? ''],
    queryFn: ({ signal }) => client!.job(id!, signal),
    retry: (count, error) => count < 2 && error instanceof ApiError && error.code === 'network',
    enabled: !!client && !!id, refetchOnWindowFocus: false, refetchOnReconnect: false,
    refetchInterval: query => query.state.error || query.state.data?.status !== 'processing' ? false : Math.max(20, pollMs),
  });
}
function requestMessage(error: unknown) {
  if (!(error instanceof ApiError)) return 'Связь с сервисом не подтверждена. Проверьте состояние ещё раз.';
  switch (error.status) {
    case 400: return 'Запрос отклонён. Проверьте ID или параметры файла.';
    case 401: return 'Ключ не принят. Сбросьте ключ и подключитесь заново.';
    case 404: return 'Задание не найдено. Проверьте ID и подключение к нужному сервису.';
    case 413: return 'Файл превышает 200 МиБ. Выберите меньший файл.';
    case 415: return 'Формат или параметры видео не поддерживаются. Проверьте ограничения.';
    case 429: return 'Сервис занят. Подождите перед новой отправкой.';
    case 503: return error.code === 'model_not_ready' ? 'Модель не готова. Обратитесь к администратору.' : 'Сервис временно недоступен. Повторите проверку позже.';
    default: return 'Состояние задания сейчас неизвестно. Повторите проверку без новой загрузки.';
  }
}
export function JobStatus({ jobId, job, checking, stage, error, authenticated = true, onRetry, onResume, onClear }: {
  jobId?: string; job?: Job; checking: boolean; stage?: string; error?: unknown; authenticated?: boolean;
  onRetry?: () => void; onResume: (id: string) => void; onClear: () => void;
}) {
  const [value, setValue] = useState(''), [invalid, setInvalid] = useState(false);
  function resume(event: FormEvent) {
    event.preventDefault();
    if (!authenticated) return;
    if (!validJobId(value.trim())) { setInvalid(true); return; }
    setInvalid(false); onResume(value.trim());
  }
  return <section className="job-panel" aria-labelledby="job-title">
    <h2 id="job-title">{jobId ? job?.status === 'done' ? 'Результат получен' : job?.status === 'failed' ? 'Анализ не завершён' : 'Обработка видео' : 'Открыть задание'}</h2>
    {jobId ? <>
      <div className="job-id"><span>ID</span><code>{jobId}</code></div>
      <p role="status">{error ? 'Текущее состояние не подтверждено.' : job?.status === 'done' ? 'События и кадры — ниже.' : job?.status === 'failed' ? reasons[job.reason] : stage ? stages[stage] ?? 'Обрабатываем видео…' : checking ? 'Проверяем состояние…' : 'Ожидаем результат…'}</p>
      <p className="muted">Сохраните ID, чтобы открыть задание позже.{(!job || job.status === 'processing') && ' Закрытие страницы не отменяет обработку.'}</p>
      <button className="text-button" onClick={onClear}>Закрыть просмотр задания</button>
    </> : <>
      <p>Введите ID ранее загруженного видео.</p>
      <form className="resume-form" onSubmit={resume}><label htmlFor="job-id">ID задания</label><div className="input-row"><input id="job-id" value={value} onChange={event => setValue(event.target.value)} placeholder="Вставьте ID задания" autoComplete="off" aria-invalid={invalid} aria-describedby={invalid ? 'job-id-error' : undefined} /><button className="secondary-button" disabled={!authenticated || !value.trim()} type="submit">Открыть</button></div>{invalid && <p id="job-id-error" role="alert" className="field-error">Неверный формат ID. Скопируйте его целиком.</p>}</form>
    </>}
    {!!error && <div role="alert" className="field-error"><p>{requestMessage(error)}</p>{onRetry && <button onClick={onRetry}>Повторить проверку</button>}</div>}
  </section>;
}
