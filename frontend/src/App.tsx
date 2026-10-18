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
  function reset(message = jobId && (!job.data || job.data.status === 'processing') ? 'Ключ удалён. Задание на сервере не отменено.' : 'Ключ удалён.') {
    activeClient.current?.dispose(); activeClient.current = undefined;
    uploadController.current?.abort(); uploadController.current = null;
    setClient(undefined); setJobId(undefined); setUploadError(undefined); setUploading(false);
    setProgress(undefined); setNotice(message); setSeek(undefined);
  }
  useEffect(() => {
    if ([model.error, job.error, diagnostics.error, uploadError].some(error => error instanceof ApiError && error.status === 401)) {
      reset('Ключ не принят. Введите действующий API-ключ.');
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
      if (error instanceof DOMException && error.name === 'AbortError') setNotice('Передача прервана. Если файл уже принят, задание продолжит обработку на сервере.');
      else setUploadError(error);
    } finally {
      if (uploadController.current === controller) uploadController.current = null;
      if (activeClient.current === current) { setUploading(false); setProgress(undefined); }
    }
  }
  const detail = diagnostics.data && diagnostics.data.job_id === jobId && diagnostics.data.public.status === job.data?.status ? diagnostics.data : undefined;
  const media = detail?.media.preview ?? detail?.media.original;
  const uploadHint = !client ? 'Сначала введите API-ключ.'
    : occupied ? job.error ? 'Восстановите связь с текущим заданием.' : 'Дождитесь завершения текущего задания.'
    : undefined;
  return <div className="app-shell">
    <a className="skip-link" href="#main">Перейти к содержимому</a>
    <aside className="sidebar">
      <a className="brand" href="#main" aria-label="Fortress, анализ видео"><svg width="30" height="32" viewBox="0 0 30 32" fill="none" aria-hidden="true"><path d="M3 3h6v6h5V3h5v6h5V3h3v21L15 30 3 24Z" stroke="currentColor" strokeWidth="2"/><path d="M11 25v-9h8v9" stroke="currentColor" strokeWidth="2"/></svg><span>FORTRESS</span></a>
      <a className="nav-active" href="#main" aria-current="page"><span aria-hidden="true">▣</span> Анализ видео</a>
      <div className="sidebar-note"><i className="dot" /> Локальная обработка</div>
    </aside>
    <div className="main-shell">
      <main id="main" tabIndex={-1}>
        <div className="page-heading"><div><h1>Анализ видео</h1><p>Загрузите запись и проверьте найденные события.</p></div></div>
        {demo && <div className="fixture-banner" role="note"><strong>Деморежим</strong> Искусственные данные. Выбранное видео не анализируется.</div>}
        {apiTest && <div className="fixture-banner" role="note"><strong>Тестовый API</strong> Используйте только искусственные ролики. Качество модели не проверено.</div>}
        {notice && <div className="notice" role="status">{notice}</div>}
        <div className="workspace-grid">
          <div className="primary-column">
            <UploadPanel key={'upload-' + (client?.session ?? 'disconnected')} enabled={canUpload} uploading={uploading} progress={progress} disabledReason={uploadHint} onUpload={upload} onAbort={() => uploadController.current?.abort()} />
            {!!uploadError && <ErrorPanel error={uploadError} />}
            {client && <JobStatus key={'job-' + client.session} jobId={jobId} job={job.data} checking={job.isFetching} error={job.error} stage={detail?.stage} authenticated={!uploading} onRetry={() => { void job.refetch(); }} onResume={id => { if (!uploading) { setJobId(id); setSeek(undefined); setUploadError(undefined); } }} onClear={() => { setJobId(undefined); setSeek(undefined); }} />}
          </div>
          <div className="secondary-column">
            <ApiKeyForm connected={!!client} onConnect={connect} onReset={() => reset()} />
            {client && <ModelStatus model={model.data} connected pending={model.isFetching} fixtureMode={demo} blocked={modelRejected} unavailable={!!model.error} />}
            {!!model.error && <ErrorPanel error={model.error} onRetry={() => { void model.refetch(); }} />}
          </div>
        </div>
        {client && job.data?.status === 'done' && <div className="result-workspace">
          <VideoPlayer key={`${client.session}-${jobId}`} client={client} path={media?.url} maxBytes={media?.max_bytes} seek={seek} />
          <EventList job={job.data} diagnostics={detail} onSeek={sourceTime => setSeek(previous => ({ sourceTime, nonce: (previous?.nonce ?? 0) + 1 }))} />
        </div>}
        {client && jobId && !!diagnostics.error && <ErrorPanel error={diagnostics.error} onRetry={() => { void diagnostics.refetch(); }} />}
      </main>
    </div>
  </div>;
}
