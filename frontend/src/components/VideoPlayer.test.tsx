import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ApiClient, ApiError } from '../api/client';
import { VideoPlayer } from './VideoPlayer';
const OriginalURL = URL;
const path = '/api/ui/v1/jobs/00000000-0000-4000-8000-000000000001/preview';
beforeEach(() => { let sequence = 0; vi.stubGlobal('URL', class extends OriginalURL { static createObjectURL = vi.fn(() => 'blob:test-' + ++sequence); static revokeObjectURL = vi.fn(); }); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function client() { const value = new ApiClient('private-test'); vi.spyOn(value, 'media').mockResolvedValue(new Blob(['synthetic'], { type: 'video/mp4' })); return value; }
test('loads authenticated Blob, releases old URL on job/key replacement and unmount', async () => {
  const first = client(), second = client(); const view = render(<VideoPlayer client={first} path={path} />);
  await screen.findByLabelText('Видео задания'); expect(first.media).toHaveBeenCalledWith(path, expect.any(AbortSignal), undefined);
  expect(screen.getByLabelText('Видео задания').getAttribute('src')).toBe('blob:test-1');
  view.rerender(<VideoPlayer client={second} path={path} />); await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalledTimes(2));
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test-1'); view.unmount(); expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test-2');
  first.dispose(); second.dispose();
});
test('seek waits for metadata then uses exact elapsed source seconds, including repeated clicks', async () => {
  const api = client(); const view = render(<VideoPlayer client={api} path={path} seek={{ sourceTime: 2.173, nonce: 1 }} />);
  const video = await screen.findByLabelText('Видео задания') as HTMLVideoElement;
  Object.defineProperty(video, 'readyState', { configurable: true, value: 1 }); Object.defineProperty(video, 'duration', { configurable: true, value: 10 });
  fireEvent.loadedMetadata(video); expect(video.currentTime).toBe(2.173);
  video.currentTime = 0; view.rerender(<VideoPlayer client={api} path={path} seek={{ sourceTime: 2.173, nonce: 2 }} />); expect(video.currentTime).toBe(2.173);
  view.rerender(<VideoPlayer client={api} path={path} seek={{ sourceTime: 11, nonce: 3 }} />); expect(screen.getByRole('alert').textContent).toContain('за пределами'); expect(video.currentTime).toBe(2.173);
  api.dispose();
});
test('ignores late media and aborts fetch when view closes', async () => {
  const api = client(); let finish!: (blob: Blob) => void; vi.mocked(api.media).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const view = render(<VideoPlayer client={api} path={path} />); const signal = vi.mocked(api.media).mock.calls[0][1]; view.unmount();
  expect(signal?.aborted).toBe(true); finish(new Blob(['late'])); await Promise.resolve(); expect(URL.createObjectURL).not.toHaveBeenCalled(); api.dispose();
});
test.each([new ApiError('media_too_large', 413), new ApiError('invalid_key', 401), new ApiError('network')])('shows local failure instead of another video', async error => {
  const api = client(); vi.mocked(api.media).mockRejectedValue(error); render(<VideoPlayer client={api} path={path} />);
  await screen.findByRole('alert'); expect(screen.queryByLabelText('Видео задания')).toBeNull(); expect(URL.createObjectURL).not.toHaveBeenCalled(); api.dispose();
});
test('browser decode failure is visible', async () => { const api = client(); render(<VideoPlayer client={api} path={path} />); fireEvent.error(await screen.findByLabelText('Видео задания')); expect(screen.getByRole('alert').textContent).toContain('не смог воспроизвести'); api.dispose(); });
