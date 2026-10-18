import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { UploadPanel } from './UploadPanel';
afterEach(cleanup);
const video = () => new File(['test'], 'clip.mp4', { type: 'video/mp4' });
test('adds multiple files locally and displays file limits', async () => {
  const onAdd = vi.fn(); render(<UploadPanel onAdd={onAdd} />);
  expect(screen.getByText(/180 с/).textContent).toContain('60 fps');
  const files = [video(), new File(['test'], 'second.mov', { type: 'video/quicktime' })];
  fireEvent.change(screen.getByLabelText('Видеофайлы'), { target: { files } });
  await waitFor(() => expect(onAdd).toHaveBeenCalledExactlyOnceWith(files));
});
test.each(['empty', 'oversize', 'unsupported'])('rejects %s without POST', async kind => {
  const onAdd = vi.fn(); render(<UploadPanel onAdd={onAdd} />);
  const file = kind === 'unsupported' ? new File(['bad'], 'bad.txt', { type: 'text/plain' }) : video();
  if (kind !== 'unsupported') Object.defineProperty(file, 'size', { value: kind === 'empty' ? 0 : 200 * 1024 * 1024 + 1 });
  fireEvent.change(screen.getByLabelText('Видеофайлы'), { target: { files: [file] } });
  await screen.findByRole('alert'); expect(onAdd).not.toHaveBeenCalled();
});
test('keeps valid files when another selected file is invalid', async () => {
  const onAdd = vi.fn(); render(<UploadPanel onAdd={onAdd} />); const file = video();
  fireEvent.change(screen.getByLabelText('Видеофайлы'), { target: { files: [file, new File(['bad'], 'bad.txt', { type: 'text/plain' })] } });
  await waitFor(() => expect(onAdd).toHaveBeenCalledExactlyOnceWith([file])); expect(screen.getByRole('alert').textContent).toContain('1');
});
test('adds pasted files to the local queue exactly once', async () => {
  const onAdd = vi.fn(); render(<UploadPanel onAdd={onAdd} />); const file = video();
  fireEvent.paste(screen.getByRole('button', { name: 'Выбрать или перетащить видео' }), { clipboardData: { files: [file], types: ['Files'], items: [{ kind: 'file', type: file.type, getAsFile: () => file }] } });
  await waitFor(() => expect(onAdd).toHaveBeenCalledExactlyOnceWith([file]));
});
