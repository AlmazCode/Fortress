import { useEffect, useRef, useState } from 'react';
import { ApiClient, ApiError } from '../api/client';
export interface SeekRequest { sourceTime: number; nonce: number }
export function VideoPlayer({ client, path, maxBytes, seek }: { client: ApiClient; path?: string; maxBytes?: number; seek?: SeekRequest }) {
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
      const message = reason instanceof ApiError && reason.code === 'media_too_large' ? 'Видео превышает разрешённый лимит памяти (не более 200 МиБ).' : reason instanceof ApiError && reason.status === 401 ? 'Для видео нужен действующий API-ключ. Сбросьте ключ и подключитесь заново.' : 'Видео недоступно или повреждено. Видеопроверка событий не выполнена.';
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
      setSeekError('Исходный таймкод находится за пределами видео. Переход не выполнен.'); return;
    }
    if (element.readyState === 0) return;
    // K/A3 previews preserve elapsed source PTS. Identity mapping in seconds;
    // neither average fps nor frame index is used, including VFR/nonzero PTS.
    try { element.currentTime = seek.sourceTime; setSeekError(''); }
    catch { setSeekError('Браузер не смог перейти к исходному таймкоду.'); }
  }
  useEffect(applySeek, [seek, current?.url, path, error]);
  return <section className="video-panel" aria-label="Видео и исходные таймкоды">
    {current && !error ? <video ref={video} src={current.url} controls preload="metadata" playsInline onLoadedMetadata={applySeek} onError={() => setFailure({ client, path, message: 'Браузер не смог воспроизвести видео. Проверка доказательств не выполнена.' })} aria-label="Видео задания" /> : <div className="video-placeholder"><span aria-hidden="true">▷</span><p>{path && !error ? 'Загружаем защищённое видео…' : 'Видео не предоставлено или недоступно'}</p></div>}
    {error && <p role="alert" className="field-error">{error}</p>}
    {seekError && <p role="alert" className="field-error">{seekError}</p>}
    <p className="muted">Таймкоды отсчитываются от начала исходного ролика. Нажмите событие или кадр, чтобы перейти к соответствующему моменту видео.</p>
  </section>;
}
