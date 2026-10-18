import { act, cleanup, fireEvent, renderHook } from '@testing-library/react';
import { probeVideo, useLocalVideoMetadata } from './useLocalVideoMetadata';
import type { QueueItem } from './useVideoQueue';
const OriginalURL = URL;
let videos: HTMLVideoElement[];
beforeEach(() => {
  videos = []; vi.stubGlobal('URL', class extends OriginalURL { static createObjectURL = vi.fn(() => 'blob:metadata-test'); static revokeObjectURL = vi.fn(); });
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {});
  const create = document.createElement.bind(document);
  vi.spyOn(document, 'createElement').mockImplementation((name, options) => { const element = create(name, options); if (name === 'video') videos.push(element as HTMLVideoElement); return element; });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage: vi.fn() } as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/jpeg;base64,cHJldmlldw==');
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
const file = new File(['synthetic'], 'local.mp4', { type: 'video/mp4' });
function metadata(video: HTMLVideoElement, duration = 7.375) {
  Object.defineProperties(video, { duration: { configurable: true, value: duration }, videoWidth: { configurable: true, value: 1920 }, videoHeight: { configurable: true, value: 1080 } });
  fireEvent.loadedMetadata(video);
}
test('reads actual browser duration and a decoded frame, then releases the source URL', async () => {
  const result = probeVideo(file, new AbortController().signal); metadata(videos[0]); fireEvent.seeked(videos[0]);
  expect(await result).toEqual({ durationSec: 7.375, thumbnail: 'data:image/jpeg;base64,cHJldmlldw==' });
  expect(URL.revokeObjectURL).toHaveBeenCalledExactlyOnceWith('blob:metadata-test');
});
test('decode failure does not invent preview or duration', async () => {
  const result = probeVideo(file, new AbortController().signal); fireEvent.error(videos[0]); expect(await result).toEqual({});
  expect(URL.revokeObjectURL).toHaveBeenCalledOnce();
});
test('timeout can retain real metadata without inventing a preview', async () => {
  vi.useFakeTimers(); const result = probeVideo(file, new AbortController().signal); metadata(videos[0]);
  vi.advanceTimersByTime(8000); expect(await result).toEqual({ durationSec: 7.375 }); expect(URL.revokeObjectURL).toHaveBeenCalledOnce();
});
test('removal and unmount abort probes, prevent late updates and revoke URLs', async () => {
  const onMetadata = vi.fn(); const items: QueueItem[] = [{ id: 'one', name: file.name, size: file.size, file, state: 'waiting' }];
  const view = renderHook(({ value }) => useLocalVideoMetadata(value, onMetadata), { initialProps: { value: items } });
  view.rerender({ value: [] }); await act(async () => { await Promise.resolve(); });
  expect(onMetadata).not.toHaveBeenCalled(); expect(URL.revokeObjectURL).toHaveBeenCalledOnce();
  view.rerender({ value: items }); view.unmount(); await Promise.resolve(); expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2);
});
