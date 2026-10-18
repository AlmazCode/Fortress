import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiClient, ApiError } from './api/client';
import { MAX_MEDIA_BYTES, type Diagnostics, type UploadProgress } from './api/types';
import { useJobPolling, failureMessages } from './components/JobStatus';
import { describeError } from './components/ErrorPanel';

export type QueueState = 'waiting' | 'uploading' | 'processing' | 'done' | 'failed' | 'uncertain';
export interface QueueItem {
  id: string; name: string; size: number; state: QueueState; file?: File; jobId?: string;
  startedAt?: number; finishedAt?: number; message?: string; events?: number;
}
export const MAX_QUEUE_FILES = 20;

export function useVideoQueue({ client, ready, onAccepted, pollMs = 1800 }: {
  client?: ApiClient; ready: boolean; onAccepted: (id: string) => void; pollMs?: number;
}) {
  const queries = useQueryClient();
  const [items, setItems] = useState<QueueItem[]>([]);
  const [running, setRunning] = useState(false);
  const [started, setStarted] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState<UploadProgress>();
  const [error, setError] = useState<unknown>();
  const [selectionNotice, setSelectionNotice] = useState('');
  const controller = useRef<AbortController | null>(null);
  const generation = useRef(0), sequence = useRef(0);
  const active = items.find(item => item.state === 'uploading' || item.state === 'processing');
  const job = useJobPolling(client, active?.jobId, pollMs);
  const diagnostics = useQuery<Diagnostics>({
    queryKey: ['fortress', client?.session ?? 0, 'diagnostics', active?.jobId ?? ''],
    queryFn: ({ signal }) => client!.diagnostics(active!.jobId!, signal),
    enabled: !!client && !!active?.jobId && !!job.data,
    retry: (count, reason) => count < 2 && reason instanceof ApiError && reason.code === 'network',
    refetchOnWindowFocus: false, refetchOnReconnect: false,
    refetchInterval: query => query.state.error || job.error || job.data?.status !== 'processing' ? false : Math.max(20, pollMs),
  });

  useEffect(() => () => { generation.current++; controller.current?.abort(); controller.current = null; }, [client]);

  useEffect(() => {
    if (!running || !ready || !client || active || uploading || controller.current) return;
    const next = items.find(item => item.state === 'waiting' && item.file);
    if (!next) { setRunning(false); return; }
    const request = new AbortController(), version = generation.current;
    controller.current = request;
    setUploading(true); setError(undefined); setProgress(undefined);
    setItems(previous => previous.map(item => item.id === next.id ? { ...item, state: 'uploading', startedAt: Date.now(), message: undefined } : item));
    void client.upload(next.file!, request.signal, value => {
      if (generation.current === version) setProgress(value);
    }).then(id => {
      if (generation.current !== version) return;
      setItems(previous => previous.map(item => item.id === next.id ? { ...item, state: 'processing', jobId: id, file: undefined } : item));
      onAccepted(id);
    }).catch(reason => {
      if (generation.current !== version) return;
      const uncertain = reason instanceof DOMException && reason.name === 'AbortError' || reason instanceof ApiError && reason.code === 'upload_outcome_unknown';
      const retryLater = reason instanceof ApiError && (reason.status === 429 || reason.status === 503);
      const message = describeError(reason);
      setItems(previous => previous.map(item => item.id === next.id ? {
        ...item, state: uncertain ? 'uncertain' : retryLater ? 'waiting' : 'failed',
        finishedAt: retryLater || uncertain ? undefined : Date.now(),
        message: `${message.title}. ${message.description}`,
      } : item));
      setError(reason);
      if (uncertain || retryLater || reason instanceof ApiError && reason.status === 401) {
        setRunning(false);
      }
    }).finally(() => {
      if (generation.current !== version) return;
      controller.current = null; setUploading(false); setProgress(undefined);
    });
  }, [running, ready, client, active, uploading, items, onAccepted]);

  useEffect(() => {
    if (!active?.jobId || !job.data || job.data.status === 'processing') return;
    const result = job.data;
    setItems(previous => previous.map(item => item.id === active.id ? {
      ...item, state: result.status, finishedAt: Date.now(),
      events: result.status === 'done' ? result.violations.length : undefined,
      message: result.status === 'failed' ? failureMessages[result.reason] : undefined,
    } : item));
    void queries.invalidateQueries({ queryKey: ['fortress', client?.session, 'diagnostics', active.jobId] });
  }, [active?.id, active?.jobId, job.data, client?.session, queries]);

  useEffect(() => { if (job.error) setRunning(false); }, [job.error]);

  function add(files: File[]) {
    const valid = files.filter(file => file.size > 0 && file.size <= MAX_MEDIA_BYTES && /\.(mp4|mov)$/i.test(file.name));
    const available = Math.max(0, MAX_QUEUE_FILES - items.length);
    const accepted = valid.slice(0, available).map(file => ({ id: `video-${++sequence.current}`, name: file.name, size: file.size, file, state: 'waiting' as const }));
    setItems(previous => [...previous, ...accepted.slice(0, Math.max(0, MAX_QUEUE_FILES - previous.length))]);
    setSelectionNotice(valid.length > available ? `В очереди может быть не больше ${MAX_QUEUE_FILES} файлов. Остальные не добавлены.`
      : valid.length !== files.length ? 'Часть файлов не добавлена: нужны непустые MP4 или MOV до 200 МиБ.' : '');
  }
  function clear() {
    generation.current++; controller.current?.abort(); controller.current = null;
    setItems([]); setRunning(false); setStarted(false); setUploading(false);
    setProgress(undefined); setError(undefined); setSelectionNotice('');
  }
  function start() {
    if (!ready) return;
    setError(undefined); setStarted(true); setRunning(true);
    if (job.error) void job.refetch();
  }
  function resume(id: string) {
    if (running || uploading || controller.current || active && active.jobId !== id) return;
    if (!items.some(item => item.jobId === id)) {
      setItems(previous => [...previous, { id: `video-${++sequence.current}`, name: `Задание ${id.slice(0, 8)}`, size: 0, state: 'processing', jobId: id }]);
    } else if (active?.jobId === id) void job.refetch();
    setError(undefined); onAccepted(id);
  }
  return {
    items, active, running, started, uploading, progress, error, selectionNotice, job, diagnostics,
    add, clear, start, resume, clearError: () => setError(undefined), pause: () => setRunning(false),
    abort: () => controller.current?.abort(),
    remove: (id: string) => setItems(previous => previous.filter(item => item.id !== id || item.state === 'uploading' || item.state === 'processing')),
    clearWaiting: () => setItems(previous => previous.filter(item => item.state !== 'waiting')),
  };
}
