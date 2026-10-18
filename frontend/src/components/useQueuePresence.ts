import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { QueueItem } from '../useVideoQueue';

export const QUEUE_EXIT_MS = 650;
export const isQueueFinished = (item: QueueItem) => item.state === 'done' || item.state === 'failed';

/** Keep an existing card mounted while its width collapses, without delaying the real queue. */
export function useQueuePresence(items: QueueItem[]) {
  const [visible, setVisible] = useState(() => items.filter(item => !isQueueFinished(item)));
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false);
  const retired = useRef(new Set(items.filter(isQueueFinished).map(item => item.id)));
  const timers = useRef(new Map<string, number>());
  const finishExit = useCallback((id: string) => {
    window.clearTimeout(timers.current.get(id)); timers.current.delete(id);
    retired.current.add(id);
    setVisible(previous => previous.filter(item => item.id !== id));
  }, []);

  useEffect(() => {
    const preference = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (!preference) return;
    const changed = () => setReducedMotion(preference.matches);
    changed(); preference.addEventListener('change', changed);
    return () => preference.removeEventListener('change', changed);
  }, []);
  useLayoutEffect(() => {
    const latest = new Map(items.map(item => [item.id, item]));
    for (const [id, timer] of timers.current) {
      if (!latest.has(id) || reducedMotion) { window.clearTimeout(timer); timers.current.delete(id); }
    }
    retired.current = new Set([...retired.current].filter(id => latest.has(id)));
    if (reducedMotion) items.filter(isQueueFinished).forEach(item => retired.current.add(item.id));
    setVisible(previous => {
      const kept = previous.filter(item => latest.has(item.id) && !retired.current.has(item.id)).map(item => latest.get(item.id)!);
      const present = new Set(kept.map(item => item.id));
      return [...kept, ...items.filter(item => !isQueueFinished(item) && !present.has(item.id))];
    });
    for (const item of items) {
      if (isQueueFinished(item) && !retired.current.has(item.id) && !timers.current.has(item.id)) {
        timers.current.set(item.id, window.setTimeout(() => finishExit(item.id), QUEUE_EXIT_MS));
      }
    }
  }, [items, reducedMotion, finishExit]);
  useEffect(() => () => { timers.current.forEach(timer => window.clearTimeout(timer)); timers.current.clear(); }, []);
  return { visible, finishExit };
}
