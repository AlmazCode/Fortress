import { useCallback, useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiClient, ApiError, type ApiTransport } from './api/client';
import { isModelReady, isPrototypeAvailable, type Diagnostics, type ModelStatusData } from './api/types';
import { ApiKeyForm } from './components/ApiKeyForm';
import { ErrorPanel } from './components/ErrorPanel';
import { ModelStatus } from './components/ModelStatus';
import { UploadPanel, type UploadHandle } from './components/UploadPanel';
import { JobStatus, useJobPolling } from './components/JobStatus';
import { EventList } from './components/EventList';
import { VideoPlayer, type SeekRequest } from './components/VideoPlayer';
import { VideoQueue } from './components/VideoQueue';
import { VideoTimeline, type Playback } from './components/VideoTimeline';
import { useVideoQueue } from './useVideoQueue';
import { useLocalVideoMetadata } from './useLocalVideoMetadata';
import { SettingsDrawer } from './components/SettingsDrawer';
import { ResultsOverview } from './components/ResultsOverview';
import { Button, Notification } from './components/ui';
const retryRead = (count: number, error: unknown) => count < 2 && error instanceof ApiError && error.code === 'network';
export default function App({ transport, fixtureMode = false, apiTestMode = false, pollMs = 1800 }: { transport?: ApiTransport; fixtureMode?: boolean; apiTestMode?: boolean; pollMs?: number }) {
  const queries = useQueryClient();
  const [client, setClient] = useState<ApiClient>();
  const [jobId, setJobId] = useState<string>();
  const [notice, setNotice] = useState('');
  const [seek, setSeek] = useState<SeekRequest>();
  const [playback, setPlayback] = useState<Playback & { jobId: string }>();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [resultOpen, setResultOpen] = useState(false);
  const uploadControl = useRef<UploadHandle>(null);
  const settingsButton = useRef<HTMLButtonElement>(null);
  const activeClient = useRef<ApiClient | undefined>(undefined);
  const resultView = useRef<HTMLElement>(null);
  const revealResult = useRef(false);
  const demo = fixtureMode && !!transport && !import.meta.env.PROD;
  const apiTest = apiTestMode && !import.meta.env.PROD;
  const model = useQuery<ModelStatusData>({
    queryKey: ['fortress', client?.session ?? 0, 'model'], queryFn: ({ signal }) => client!.model(signal),
    enabled: !!client, retry: retryRead, refetchOnWindowFocus: false, refetchOnReconnect: false,
  });
  const onAccepted = useCallback((id: string) => setJobId(previous => previous ?? id), []);
  const ready = !!client && !model.isFetching && !model.error && (demo || isModelReady(model.data) || isPrototypeAvailable(model.data) || apiTest && model.data?.test_only === true && !model.data.trained && !model.data.validated);
  const queue = useVideoQueue({ client, ready, onAccepted, pollMs });
  useLocalVideoMetadata(queue.items, queue.setMediaInfo);
  const viewingActive = !!jobId && jobId === queue.active?.jobId;
  const history = useJobPolling(client, viewingActive ? undefined : jobId, pollMs);
  const job = viewingActive ? queue.job : history;
  useEffect(() => {
    if (revealResult.current && job.data?.status === 'done' && job.data.job_id === jobId && resultView.current) {
      revealResult.current = false;
      resultView.current.scrollIntoView?.({ block: 'start' });
      resultView.current.focus({ preventScroll: true });
    }
  }, [jobId, job.data?.status, job.data?.job_id, resultOpen]);
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
    setResultOpen(false);
  }
  useEffect(() => {
    if ([model.error, job.error, diagnostics.error, queue.error, queue.job.error, queue.diagnostics.error].some(error => error instanceof ApiError && error.status === 401)) {
      reset('Ключ не принят. Введите действующий API-ключ.');
      openSettings();
    }
  }, [model.error, job.error, diagnostics.error, queue.error, queue.job.error, queue.diagnostics.error]);
  function connect(key: string) {
    revealResult.current = false;
    if (activeClient.current) queue.clear();
    activeClient.current?.dispose();
    const next = new ApiClient(key, transport, queries); activeClient.current = next;
    setClient(next); setJobId(undefined); setSeek(undefined); setPlayback(undefined); setNotice('');
    setResultOpen(false);
  }
  function viewJob(id: string) {
    revealResult.current = true;
    if (resultOpen && id === jobId && job.data?.status === 'done' && resultView.current) {
      resultView.current?.scrollIntoView?.({ block: 'start' });
      resultView.current?.focus({ preventScroll: true });
      revealResult.current = false;
    }
    setJobId(id); setSeek(undefined); setPlayback(undefined);
    setResultOpen(true);
  }
  function openSettings() {
    setSettingsOpen(true);
  }
  function clearQueue() {
    if (queue.active || queue.running) return;
    queue.clearPending();
  }
  function clearResults() {
    const selected = queue.items.find(item => item.jobId === jobId);
    queue.clearFinished();
    if (selected?.state === 'done' || selected?.state === 'failed') {
      revealResult.current = false; setJobId(undefined); setSeek(undefined); setPlayback(undefined); setResultOpen(false);
    }
  }
  const modelRejected = queue.error instanceof ApiError && queue.error.code === 'model_not_ready';
  const detail = diagnostics.data && diagnostics.data.job_id === jobId && diagnostics.data.public.status === job.data?.status ? diagnostics.data : undefined;
  const media = detail?.media.preview ?? detail?.media.original;
  const blockedReason = !client ? 'Добавьте API-ключ в настройках, чтобы запустить очередь.' : model.isFetching ? 'Проверяем готовность модели…' : model.error ? 'Восстановите подключение к сервису.' : !ready || modelRejected ? 'Подключите обученную модель в настройках, чтобы начать анализ.' : undefined;
  return <div className="app-shell">
    <a className="skip-link" href="#main">Перейти к содержимому</a>
    <header className="app-topbar"><div className="topbar-inner"><a className="brand" href="#main" aria-label="Fortress, анализ видео"><svg width="30" height="32" viewBox="0 0 30 32" fill="none" aria-hidden="true"><path d="M3 3h6v6h5V3h5v6h5V3h3v21L15 30 3 24Z" stroke="currentColor" strokeWidth="2"/><path d="M11 25v-9h8v9" stroke="currentColor" strokeWidth="2"/></svg><span>FORTRESS</span></a></div></header>
    <main id="main" tabIndex={-1}>
      <div className="page-heading"><div><h1>Анализ видео</h1><p>Загрузите видео, чтобы найти возможные нарушения и просмотреть события с таймкодами</p></div><Button ref={settingsButton} icon="settings" aria-haspopup="dialog" aria-expanded={settingsOpen} aria-controls="analysis-settings" onClick={openSettings}>Настройки</Button></div>
      {demo && <Notification tone="warning" role="note" className="demo-notice">Деморежим: показаны примеры результатов, загруженные видео не анализируются</Notification>}
      {apiTest && <Notification tone="warning" role="note">Тестовый API. Используйте только искусственные ролики. Качество модели не проверено.</Notification>}
      {notice && <Notification>{notice}</Notification>}
      <section className="video-workbench" aria-label="Загрузка и очередь видео">
        <UploadPanel controlRef={uploadControl} onAdd={queue.add} busy={queue.uploading} compact={queue.items.length > 0} />
        {queue.selectionNotice && <Notification tone="danger" role="alert">{queue.selectionNotice}</Notification>}
        <VideoQueue items={queue.items} active={queue.active} running={queue.running} started={queue.started} canStart={ready && !modelRejected} blockedReason={blockedReason} progress={queue.progress} diagnostics={queue.diagnostics.data} connectionLost={!!queue.job.error} onStart={queue.start} onPause={queue.pause} onAbort={queue.abort} onRemove={queue.remove} onClear={clearQueue} onSettings={openSettings} />
        {!!queue.error && <ErrorPanel error={queue.error} />}
      </section>
      <ResultsOverview items={queue.items} onView={viewJob} onChooseFiles={() => uploadControl.current?.open()} onClear={clearResults} primaryAction={!queue.items.some(item => item.state !== 'done' && item.state !== 'failed')} />
      {client && resultOpen && job.data?.status === 'done' && <section className="result-workspace" ref={resultView} tabIndex={-1} aria-label="Просмотр результата видео">
        <div className="result-heading"><div><span className="eyebrow">Просмотр результата</span><h2>{queue.items.find(item => item.jobId === jobId)?.name ?? 'Результат задания'}</h2></div><Button onClick={() => { setResultOpen(false); const item = queue.items.find(entry => entry.jobId === jobId); if (item) document.getElementById(`result-${item.id}`)?.focus(); }}>К списку результатов</Button></div>
        <div className="review-layout"><div className="video-review"><VideoPlayer key={`${client.session}-${jobId}`} client={client} path={media?.url} maxBytes={media?.max_bytes} seek={seek} onPlaybackChange={next => { if (jobId) setPlayback({ ...next, jobId }); }} />
        <VideoTimeline job={job.data} diagnostics={detail} playback={playback?.jobId === jobId ? playback : undefined} selectedTime={seek?.sourceTime} onSeek={sourceTime => setSeek(previous => ({ sourceTime, nonce: (previous?.nonce ?? 0) + 1 }))} /></div>
        <EventList job={job.data} diagnostics={detail} onSeek={sourceTime => setSeek(previous => ({ sourceTime, nonce: (previous?.nonce ?? 0) + 1 }))} /></div>
      </section>}
      {client && resultOpen && jobId && !!diagnostics.error && <ErrorPanel error={diagnostics.error} onRetry={() => { void diagnostics.refetch(); }} />}
    </main>
    <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} returnFocus={settingsButton}>
      <ApiKeyForm connected={!!client} onConnect={connect} onReset={() => reset()} />
      <ModelStatus model={model.data} connected={!!client} pending={!!client && model.isFetching} fixtureMode={demo} blocked={modelRejected} unavailable={!!model.error} onRefresh={() => { queue.clearError(); void model.refetch(); }} />
      {!!model.error && <ErrorPanel error={model.error} onRetry={() => { void model.refetch(); }} />}
      <JobStatus key={'job-' + (client?.session ?? 0)} jobId={jobId} job={job.data} checking={job.isFetching} error={job.error} stage={detail?.stage} authenticated={!!client && !queue.active && !queue.running} onRetry={() => { void job.refetch(); }} onResume={id => { if (client && !queue.active && !queue.running) { queue.resume(id); viewJob(id); setSettingsOpen(false); } }} onClear={() => { revealResult.current = false; setJobId(undefined); setSeek(undefined); setPlayback(undefined); setResultOpen(false); }} />
    </SettingsDrawer>
  </div>;
}
