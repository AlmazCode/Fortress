import { useEffect, useRef } from 'react';
import type { QueueItem } from './useVideoQueue';

export interface LocalVideoMetadata { durationSec?: number; thumbnail?: string }
export function probeVideo(file: File, signal: AbortSignal): Promise<LocalVideoMetadata> {
  return new Promise(resolve => {
    if (signal.aborted) { resolve({}); return; }
    const video = document.createElement('video');
    const url = URL.createObjectURL(file);
    let settled = false, seekingPreview = false;
    const result: LocalVideoMetadata = {};
    const timer = window.setTimeout(finish, 8000);
    function finish() {
      if (settled) return;
      settled = true; window.clearTimeout(timer);
      signal.removeEventListener('abort', finish);
      video.onloadedmetadata = null; video.onloadeddata = null; video.onseeked = null; video.onerror = null;
      video.removeAttribute('src'); video.load(); URL.revokeObjectURL(url);
      resolve(signal.aborted ? {} : result);
    }
    video.preload = 'metadata'; video.muted = true; video.playsInline = true;
    video.onloadedmetadata = () => {
      if (Number.isFinite(video.duration) && video.duration > 0) {
        result.durationSec = video.duration;
        try { seekingPreview = true; video.currentTime = Math.min(.1, video.duration / 2); }
        catch { seekingPreview = false; }
      }
    };
    function capture() {
      if (settled) return;
      if (video.videoWidth > 0 && video.videoHeight > 0) {
        try {
          const canvas = document.createElement('canvas'); canvas.width = 240; canvas.height = Math.max(1, Math.round(240 * video.videoHeight / video.videoWidth));
          const context = canvas.height <= 480 ? canvas.getContext('2d') : null;
          if (context) { context.drawImage(video, 0, 0, canvas.width, canvas.height); const value = canvas.toDataURL('image/jpeg', .7); if (value.startsWith('data:image/jpeg;')) result.thumbnail = value; }
        } catch { /* A missing preview never substitutes evidence or rejects server-decodable media. */ }
      }
      finish();
    }
    video.onloadeddata = () => { if (!seekingPreview) capture(); };
    video.onseeked = capture;
    video.onerror = finish; signal.addEventListener('abort', finish, { once: true }); video.src = url;
  });
}
export function useLocalVideoMetadata(items: QueueItem[], onMetadata: (id: string, metadata: LocalVideoMetadata) => void) {
  const probes = useRef(new Map<string, AbortController>());
  useEffect(() => {
    const ids = new Set(items.map(item => item.id));
    for (const [id, controller] of probes.current) if (!ids.has(id)) { controller.abort(); probes.current.delete(id); }
    for (const item of items) {
      if (!item.file || probes.current.has(item.id)) continue;
      const controller = new AbortController(); probes.current.set(item.id, controller);
      void probeVideo(item.file, controller.signal).then(value => { if (!controller.signal.aborted) onMetadata(item.id, value); });
    }
  }, [items, onMetadata]);
  useEffect(() => () => { probes.current.forEach(controller => controller.abort()); probes.current.clear(); }, []);
}
