import { useEffect, useRef, useState } from 'react';
import { ApiClient, ApiError } from '../api/client';
import type { Playback } from './VideoTimeline';
export interface SeekRequest { sourceTime: number; nonce: number }
export function VideoPlayer({ client, path, maxBytes, seek, onPlaybackChange }: { client: ApiClient; path?: string; maxBytes?: number; seek?: SeekRequest; onPlaybackChange?: (playback: Playback) => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [loaded, setLoaded] = useState<{ client: ApiClient; path: string; url: string }>();
  const [failure, setFailure] = useState<{ client: ApiClient; path?: string; message: string }>();
  const [seekError, setSeekError] = useState('');
  const current = loaded?.client === client && loaded.path === path ? loaded : undefined;
  const error = failure?.client === client && failure.path === path ? failure.message : undefined;
  useEffect(() => {
    let active = true, created: string | undefined;
    const controller = new AbortController();
    setLoaded(undefined); setFailure(undefined); setSeekError('');
    if (path) void client.media(path, controller.signal, maxBytes).then(blob => {
      if (!active) return;
      created = URL.createObjectURL(blob); setLoaded({ client, path, url: created });
    }).catch(reason => {
      if (!active || reason?.name === 'AbortError') return;
      const message = reason instanceof ApiError && reason.code === 'media_too_large' ? 'Видео превышает лимит 200 МиБ.' : reason instanceof ApiError && reason.status === 401 ? 'Ключ не принят. Подключитесь заново.' : 'Не удалось загрузить видео.';
      setFailure({ client, path, message });
    });
    return () => { active = false; controller.abort(); if (created) URL.revokeObjectURL(created); };
  }, [client, path, maxBytes]);
  function applySeek() {
    const element = video.current;
    if (!seek) return;
    if (!element || !current) {
      if (!path || error) setSeekError('Переход недоступен: видео не получено.');
      return;
    }
    if (!Number.isFinite(seek.sourceTime) || seek.sourceTime < 0 || Number.isFinite(element.duration) && seek.sourceTime > element.duration) {
      setSeekError('Таймкод за пределами видео.'); return;
    }
    if (element.readyState === 0) return;
    // K/A3 previews preserve elapsed source PTS. Identity mapping in seconds;
    // neither average fps nor frame index is used, including VFR/nonzero PTS.
    try { element.currentTime = seek.sourceTime; setSeekError(''); reportPlayback(); }
    catch { setSeekError('Браузер не смог перейти к исходному таймкоду.'); }
  }
  function reportPlayback() {
    const element = video.current;
    if (current && !error && element && Number.isFinite(element.currentTime) && Number.isFinite(element.duration) && element.duration > 0) {
      onPlaybackChange?.({ time: element.currentTime, duration: element.duration });
    }
  }
  useEffect(applySeek, [seek, current?.url, path, error]);
  return <section className="video-panel" aria-label="Видео и исходные таймкоды">
    {current && !error ? <video ref={video} src={current.url} controls preload="metadata" playsInline onLoadedMetadata={() => { applySeek(); reportPlayback(); }} onTimeUpdate={reportPlayback} onDurationChange={reportPlayback} onError={() => setFailure({ client, path, message: 'Браузер не смог воспроизвести видео.' })} aria-label="Видео задания" /> : <div className="video-placeholder"><span aria-hidden="true">▷</span><p role={error ? 'alert' : undefined}>{error ?? (path ? 'Загружаем видео…' : 'Видео не предоставлено')}</p></div>}
    {seekError && <p role="alert" className="field-error">{seekError}</p>}
  </section>;
}
