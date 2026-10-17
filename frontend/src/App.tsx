import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiClient, ApiError, type ApiTransport } from './api/client';
import { isModelReady, type Diagnostics, type ModelStatusData, type UploadProgress } from './api/types';
import { ApiKeyForm } from './components/ApiKeyForm';
import { ErrorPanel } from './components/ErrorPanel';
import { ModelStatus } from './components/ModelStatus';
import { UploadPanel } from './components/UploadPanel';
import { JobStatus, useJobPolling } from './components/JobStatus';
import { EventList } from './components/EventList';
import { VideoPlayer, type SeekRequest } from './components/VideoPlayer';
const retryRead = (count: number, error: unknown) => count < 2 && error instanceof ApiError && error.code === 'network';
export default function App({ transport, fixtureMode = false, apiTestMode = false, pollMs = 1800 }: { transport?: ApiTransport; fixtureMode?: boolean; apiTestMode?: boolean; pollMs?: number }) {
  const queries = useQueryClient();
  const [client, setClient] = useState<ApiClient>();
  const [jobId, setJobId] = useState<string>();
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState<UploadProgress>();
  const [uploadError, setUploadError] = useState<unknown>();
  const [notice, setNotice] = useState('');
  const [seek, setSeek] = useState<SeekRequest>();
  const uploadController = useRef<AbortController | null>(null);
  const activeClient = useRef<ApiClient | undefined>(undefined);
  const demo = fixtureMode && !!transport && !import.meta.env.PROD;
  const apiTest = apiTestMode && !import.meta.env.PROD;
  const model = useQuery<ModelStatusData>({
    queryKey: ['fortress', client?.session ?? 0, 'model'], queryFn: ({ signal }) => client!.model(signal),
    enabled: !!client, retry: retryRead, refetchOnWindowFocus: false, refetchOnReconnect: false,
  });
  const job = useJobPolling(client, jobId, pollMs);
  const diagnostics = useQuery<Diagnostics>({
    queryKey: ['fortress', client?.session ?? 0, 'diagnostics', jobId ?? ''],
    queryFn: ({ signal }) => client!.diagnostics(jobId!, signal), enabled: !!client && !!jobId && !!job.data,
    retry: retryRead, refetchOnWindowFocus: false, refetchOnReconnect: false,
    refetchInterval: query => query.state.error || job.error || job.data?.status !== 'processing' ? false : Math.max(20, pollMs),
  });
  useEffect(() => () => { uploadController.current?.abort(); activeClient.current?.dispose(); }, []);
  useEffect(() => {
    if (client && jobId && (job.data?.status === 'done' || job.data?.status === 'failed')) {
      void queries.invalidateQueries({ queryKey: ['fortress', client.session, 'diagnostics', jobId] });
    }
  }, [client, jobId, job.data?.status, queries]);
  function reset(message = 'Сеанс очищен. Принятое сервером задание продолжает обработку.') {
    activeClient.current?.dispose(); activeClient.current = undefined;
    uploadController.current?.abort(); uploadController.current = null;
    setClient(undefined); setJobId(undefined); setUploadError(undefined); setUploading(false);
    setProgress(undefined); setNotice(message); setSeek(undefined);
  }
  useEffect(() => {
    if ([model.error, job.error, diagnostics.error, uploadError].some(error => error instanceof ApiError && error.status === 401)) {
      reset('Ключ не принят. Введите действующий API-ключ. Принятые сервером задания не отменены.');
    }
  }, [model.error, job.error, diagnostics.error, uploadError]);
  function connect(key: string) {
    activeClient.current?.dispose();
    const next = new ApiClient(key, transport, queries); activeClient.current = next;
    setClient(next); setJobId(undefined); setSeek(undefined); setUploadError(undefined); setNotice('');
  }
  const modelRejected = uploadError instanceof ApiError && uploadError.code === 'model_not_ready';
  const outcomeUnknown = uploadError instanceof ApiError && uploadError.code === 'upload_outcome_unknown';
  const occupied = !!jobId && (!job.data || !!job.error || job.data.status === 'processing');
  const canUpload = !!client && !model.isFetching && !model.error && !modelRejected && !outcomeUnknown &&
    (demo || isModelReady(model.data) || apiTest && model.data?.test_only === true && !model.data.trained && !model.data.validated) && !uploading && !occupied;
  async function upload(file: File) {
    if (!client || !canUpload || uploadController.current) return;
    const current = client, controller = new AbortController(); uploadController.current = controller;
    setJobId(undefined); setSeek(undefined); setUploading(true); setProgress(undefined); setUploadError(undefined); setNotice('');
    try {
      const id = await current.upload(file, controller.signal, value => { if (activeClient.current === current) setProgress(value); });
      if (activeClient.current === current) setJobId(id);
    } catch (error) {
      if (activeClient.current !== current) return;
      if (error instanceof DOMException && error.name === 'AbortError') setNotice('Связь прервана. Если сервер успел принять файл, задание не отменено. Откройте его по известному ID.');
      else setUploadError(error);
    } finally {
      if (uploadController.current === controller) uploadController.current = null;
      if (activeClient.current === current) { setUploading(false); setProgress(undefined); }
    }
  }
  const detail = diagnostics.data && diagnostics.data.job_id === jobId && diagnostics.data.public.status === job.data?.status ? diagnostics.data : undefined;
  const media = detail?.media.preview ?? detail?.media.original;
  return <div className="app-shell">
    <a className="skip-link" href="#main">Перейти к содержимому</a>
    <aside className="sidebar">
      <a className="brand" href="#main" aria-label="Fortress, анализ видео"><svg width="30" height="32" viewBox="0 0 30 32" fill="none" aria-hidden="true"><path d="M3 3h6v6h5V3h5v6h5V3h3v21L15 30 3 24Z" stroke="currentColor" strokeWidth="2"/><path d="M11 25v-9h8v9" stroke="currentColor" strokeWidth="2"/></svg><span>FORTRESS<small>VIDEO INTELLIGENCE</small></span></a>
      <div className="sidebar-label">РАБОЧЕЕ ПРОСТРАНСТВО</div><div className="nav-active"><span aria-hidden="true">▣</span> Анализ видео <span className="nav-arrow" aria-hidden="true">↗</span></div>
      <div className="sidebar-note"><span className="sidebar-note-icon" aria-hidden="true">◇</span><strong>Внутри вашего контура</strong><p>Обработка видео, медиа и веса остаются на локальном сервисе.</p><div><i className="dot" /> Без облачного AI</div></div>
      <div className="sidebar-footer"><span className="workspace-avatar">F</span><div>Локальное окружение<small>Проверка оператором</small></div></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><span>Рабочее пространство <span aria-hidden="true">/</span> <strong>Анализ видео</strong></span><div className="topbar-session"><i className={`dot ${client ? 'green' : ''}`} />{client ? 'Ключ подключён' : 'Сеанс не подключён'}</div></header>
      <main id="main" tabIndex={-1}>
        <div className="page-heading"><div><div className="section-eyebrow">КОНТРОЛЬ ОПЕРАЦИЙ</div><h1>Каждый вывод —<br className="mobile-break" /> с доказательством.</h1><p>Загрузите запись, проверьте наблюдаемые события<br className="desktop-break" /> и сопоставьте выводы с исходными кадрами.</p></div><div className="page-index" aria-hidden="true">01<span>VIDEO REVIEW</span></div></div>
        {demo && <div className="fixture-banner" role="note"><strong>SYNTHETIC TEST / DEMO</strong> Искусственные примеры. Модель, нормы и реальное качество не проверены. Исходное видео в этом режиме не обрабатывается.</div>}
        {apiTest && <div className="fixture-banner" role="note"><strong>SYNTHETIC API TEST</strong> Настоящий локальный API в тестовом режиме. Используйте только искусственные тестовые ролики. Модель и реальное качество не проверены; этот режим не подтверждает готовность production.</div>}
        <div className="steps" aria-label="Этапы проверки"><div className="step current"><span>01</span><div><strong>Загрузите видео</strong><small>Исходная запись MP4 / MOV</small></div></div><div className={`step ${jobId ? 'current' : ''}`}><span>02</span><div><strong>Дождитесь обработки</strong><small>Проверка состояния задания</small></div></div><div className={`step ${job.data?.status === 'done' ? 'current' : ''}`}><span>03</span><div><strong>Проверьте события</strong><small>Таймкоды, кадры, ограничения</small></div></div></div>
        {notice && <div className="notice" role="status">{notice}</div>}
        <div className="workspace-grid">
          <div className="primary-column">
            <UploadPanel key={'upload-' + (client?.session ?? 'disconnected')} enabled={canUpload} uploading={uploading} progress={progress} onUpload={upload} onAbort={() => uploadController.current?.abort()} />
            {!!uploadError && <ErrorPanel error={uploadError} />}
            {client && <JobStatus key={'job-' + client.session} jobId={jobId} job={job.data} checking={job.isFetching} error={job.error} stage={detail?.stage} authenticated={!uploading} onRetry={() => { void job.refetch(); }} onResume={id => { if (!uploading) { setJobId(id); setSeek(undefined); setUploadError(undefined); } }} onClear={() => { setJobId(undefined); setSeek(undefined); }} />}
          </div>
          <div className="secondary-column">
            <ApiKeyForm connected={!!client} onConnect={connect} onReset={() => reset()} fixtureMode={demo || apiTest} />
            <ModelStatus model={model.data} connected={!!client} pending={model.isFetching} fixtureMode={demo || apiTest} blocked={modelRejected || !!model.error} />
            {!!model.error && <ErrorPanel error={model.error} onRetry={() => { void model.refetch(); }} />}
            <div className="operator-note"><span aria-hidden="true">↗</span><p><strong>Оператор принимает решение.</strong> Сервис помогает найти наблюдаемые события. Невидимое и неподдерживаемое остаётся неизвестным.</p></div>
          </div>
        </div>
        {client && job.data?.status === 'done' && <div className="result-workspace">
          <div className="section-eyebrow">ИСХОДНАЯ ЗАПИСЬ / СВЕРКА</div>
          <VideoPlayer key={`${client.session}-${jobId}`} client={client} path={media?.url} maxBytes={media?.max_bytes} seek={seek} />
          <EventList job={job.data} diagnostics={detail} onSeek={sourceTime => setSeek(previous => ({ sourceTime, nonce: (previous?.nonce ?? 0) + 1 }))} />
        </div>}
        {client && jobId && !!diagnostics.error && <ErrorPanel error={diagnostics.error} onRetry={() => { void diagnostics.refetch(); }} />}
        <footer className="page-footer"><span>FORTRESS <span aria-hidden="true">/</span> Локальная видеоаналитика</span><span>Наблюдение → проверка → решение</span></footer>
      </main>
    </div>
  </div>;
}
