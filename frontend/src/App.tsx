import { useCallback, useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiClient, ApiError, type ApiTransport } from './api/client';
import { isModelReady, type Diagnostics, type ModelStatusData } from './api/types';
import { ApiKeyForm } from './components/ApiKeyForm';
import { ErrorPanel } from './components/ErrorPanel';
import { ModelStatus } from './components/ModelStatus';
import { UploadPanel } from './components/UploadPanel';
import { JobStatus, useJobPolling } from './components/JobStatus';
import { EventList } from './components/EventList';
import { VideoPlayer, type SeekRequest } from './components/VideoPlayer';
import { VideoQueue } from './components/VideoQueue';
import { VideoTimeline, type Playback } from './components/VideoTimeline';
import { useVideoQueue } from './useVideoQueue';
const retryRead = (count: number, error: unknown) => count < 2 && error instanceof ApiError && error.code === 'network';
export default function App({ transport, fixtureMode = false, apiTestMode = false, pollMs = 1800 }: { transport?: ApiTransport; fixtureMode?: boolean; apiTestMode?: boolean; pollMs?: number }) {
  const queries = useQueryClient();
  const [client, setClient] = useState<ApiClient>();
  const [jobId, setJobId] = useState<string>();
  const [notice, setNotice] = useState('');
  const [seek, setSeek] = useState<SeekRequest>();
  const [playback, setPlayback] = useState<Playback & { jobId: string }>();
  const activeClient = useRef<ApiClient | undefined>(undefined);
  const resultView = useRef<HTMLDivElement>(null);
  const revealResult = useRef(false);
  const demo = fixtureMode && !!transport && !import.meta.env.PROD;
  const apiTest = apiTestMode && !import.meta.env.PROD;
  const model = useQuery<ModelStatusData>({
    queryKey: ['fortress', client?.session ?? 0, 'model'], queryFn: ({ signal }) => client!.model(signal),
    enabled: !!client, retry: retryRead, refetchOnWindowFocus: false, refetchOnReconnect: false,
  });
  const onAccepted = useCallback((id: string) => setJobId(previous => previous ?? id), []);
  const ready = !!client && !model.isFetching && !model.error && (demo || isModelReady(model.data) || apiTest && model.data?.test_only === true && !model.data.trained && !model.data.validated);
  const queue = useVideoQueue({ client, ready, onAccepted, pollMs });
  const viewingActive = !!jobId && jobId === queue.active?.jobId;
  const history = useJobPolling(client, viewingActive ? undefined : jobId, pollMs);
  const job = viewingActive ? queue.job : history;
  useEffect(() => {
    if (revealResult.current && job.data?.status === 'done' && job.data.job_id === jobId && resultView.current) {
      revealResult.current = false;
      resultView.current.scrollIntoView?.({ block: 'start' });
      resultView.current.focus({ preventScroll: true });
    }
  }, [jobId, job.data?.status, job.data?.job_id]);
  const historyDiagnostics = useQuery<Diagnostics>({
    queryKey: ['fortress', client?.session ?? 0, 'diagnostics', jobId ?? ''],
    queryFn: ({ signal }) => client!.diagnostics(jobId!, signal), enabled: !viewingActive && !!client && !!jobId && !!job.data,
    retry: retryRead, refetchOnWindowFocus: false, refetchOnReconnect: false,
    refetchInterval: query => query.state.error || job.error || job.data?.status !== 'processing' ? false : Math.max(20, pollMs),
  });
  const diagnostics = viewingActive ? queue.diagnostics : historyDiagnostics;
  useEffect(() => () => { activeClient.current?.dispose(); }, []);
  function reset(message = queue.active?.jobId ? 'Ключ удалён, очередь очищена. Принятое задание не отменено.' : 'Ключ удалён, очередь очищена.') {
    revealResult.current = false;
    queue.clear();
    activeClient.current?.dispose(); activeClient.current = undefined;
    setClient(undefined); setJobId(undefined); setNotice(message); setSeek(undefined); setPlayback(undefined);
  }
  useEffect(() => {
    if ([model.error, job.error, diagnostics.error, queue.error, queue.job.error, queue.diagnostics.error].some(error => error instanceof ApiError && error.status === 401)) {
      reset('Ключ не принят. Введите действующий API-ключ.');
    }
  }, [model.error, job.error, diagnostics.error, queue.error, queue.job.error, queue.diagnostics.error]);
  function connect(key: string) {
    revealResult.current = false;
    if (activeClient.current) queue.clear();
    activeClient.current?.dispose();
    const next = new ApiClient(key, transport, queries); activeClient.current = next;
    setClient(next); setJobId(undefined); setSeek(undefined); setPlayback(undefined); setNotice('');
  }
  function viewJob(id: string) {
    revealResult.current = true;
    if (id === jobId && job.data?.status === 'done') {
      resultView.current?.scrollIntoView?.({ block: 'start' });
      resultView.current?.focus({ preventScroll: true });
      revealResult.current = false;
    }
    setJobId(id); setSeek(undefined); setPlayback(undefined);
  }
  const modelRejected = queue.error instanceof ApiError && queue.error.code === 'model_not_ready';
  const detail = diagnostics.data && diagnostics.data.job_id === jobId && diagnostics.data.public.status === job.data?.status ? diagnostics.data : undefined;
  const media = detail?.media.preview ?? detail?.media.original;
  const blockedReason = !client ? 'Введите API-ключ, чтобы запустить очередь.' : model.isFetching ? 'Проверяем готовность модели…' : model.error ? 'Восстановите подключение к сервису.' : !ready || modelRejected ? 'Подключите обученную модель, чтобы начать анализ.' : undefined;
  return <div className="app-shell">
    <a className="skip-link" href="#main">Перейти к содержимому</a>
    <aside className="sidebar">
      <a className="brand" href="#main" aria-label="Fortress, анализ видео"><svg width="30" height="32" viewBox="0 0 30 32" fill="none" aria-hidden="true"><path d="M3 3h6v6h5V3h5v6h5V3h3v21L15 30 3 24Z" stroke="currentColor" strokeWidth="2"/><path d="M11 25v-9h8v9" stroke="currentColor" strokeWidth="2"/></svg><span>FORTRESS</span></a>
      <a className="nav-active" href="#main" aria-current="page"><span aria-hidden="true">▣</span> Анализ видео</a>
      <div className="sidebar-note"><i className="dot" /> Локальная обработка</div>
    </aside>
    <div className="main-shell">
      <main id="main" tabIndex={-1}>
        <div className="page-heading"><div><h1>Анализ видео</h1><p>Добавьте записи в очередь и следите за обработкой.</p></div></div>
        {demo && <div className="fixture-banner" role="note"><strong>Деморежим</strong> Искусственные данные. Выбранное видео не анализируется.</div>}
        {apiTest && <div className="fixture-banner" role="note"><strong>Тестовый API</strong> Используйте только искусственные ролики. Качество модели не проверено.</div>}
        {notice && <div className="notice" role="status">{notice}</div>}
        <div className="workspace-grid">
          <div className="primary-column">
            <UploadPanel onAdd={queue.add} />
            {queue.selectionNotice && <p className="field-error" role="alert">{queue.selectionNotice}</p>}
            <VideoQueue items={queue.items} active={queue.active} running={queue.running} started={queue.started} canStart={ready && !modelRejected} blockedReason={blockedReason} progress={queue.progress} diagnostics={queue.diagnostics.data} connectionLost={!!queue.job.error} onStart={queue.start} onPause={queue.pause} onAbort={queue.abort} onRemove={queue.remove} onClearWaiting={queue.clearWaiting} onView={viewJob} />
            {!!queue.error && <ErrorPanel error={queue.error} />}
          </div>
          <div className="secondary-column">
            <ApiKeyForm connected={!!client} onConnect={connect} onReset={() => reset()} />
            {client && <ModelStatus model={model.data} connected pending={model.isFetching} fixtureMode={demo} blocked={modelRejected} unavailable={!!model.error} onRefresh={() => { queue.clearError(); void model.refetch(); }} />}
            {!!model.error && <ErrorPanel error={model.error} onRetry={() => { void model.refetch(); }} />}
            {client && <details className="job-access" open={!!job.error || job.data?.status === 'failed'}><summary>Задание по ID</summary><JobStatus key={'job-' + client.session} jobId={jobId} job={job.data} checking={job.isFetching} error={job.error} stage={detail?.stage} authenticated={!queue.active && !queue.running} onRetry={() => { void job.refetch(); }} onResume={id => { if (!queue.active && !queue.running) { queue.resume(id); viewJob(id); } }} onClear={() => { revealResult.current = false; setJobId(undefined); setSeek(undefined); setPlayback(undefined); }} /></details>}
          </div>
        </div>
        {client && job.data?.status === 'done' && <div className="result-workspace" ref={resultView} tabIndex={-1} aria-label="Результат анализа видео">
          <div className="result-heading"><h2>Результат анализа</h2><p>{queue.items.find(item => item.jobId === jobId)?.name}</p></div>
          <div className="video-review"><VideoPlayer key={`${client.session}-${jobId}`} client={client} path={media?.url} maxBytes={media?.max_bytes} seek={seek} onPlaybackChange={next => { if (jobId) setPlayback({ ...next, jobId }); }} />
          <VideoTimeline job={job.data} diagnostics={detail} playback={playback?.jobId === jobId ? playback : undefined} selectedTime={seek?.sourceTime} onSeek={sourceTime => setSeek(previous => ({ sourceTime, nonce: (previous?.nonce ?? 0) + 1 }))} /></div>
          <EventList job={job.data} diagnostics={detail} onSeek={sourceTime => setSeek(previous => ({ sourceTime, nonce: (previous?.nonce ?? 0) + 1 }))} />
        </div>}
        {client && jobId && !!diagnostics.error && <ErrorPanel error={diagnostics.error} onRetry={() => { void diagnostics.refetch(); }} />}
      </main>
    </div>
  </div>;
}
