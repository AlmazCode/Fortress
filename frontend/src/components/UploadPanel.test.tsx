import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { UploadPanel } from './UploadPanel';
afterEach(cleanup);
const video = () => new File(['test'], 'clip.mp4', { type: 'video/mp4' });
const props = { enabled: true, uploading: false, onUpload: vi.fn(), onAbort: vi.fn() };
test('shows limits and submits only after explicit selection and click', async () => {
  const onUpload = vi.fn(); render(<UploadPanel {...props} onUpload={onUpload} />);
  expect(screen.getByText(/180 с/).textContent).toContain('60 fps');
  expect((screen.getByRole('button', { name: /Начать анализ/ }) as HTMLButtonElement).disabled).toBe(true);
  const file = video(); fireEvent.change(screen.getByLabelText('Видеофайл'), { target: { files: [file] } });
  await screen.findByText(file.name); expect(onUpload).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: /Начать анализ/ })); expect(onUpload).toHaveBeenCalledExactlyOnceWith(file);
});
test.each(['empty', 'oversize', 'unsupported'])('rejects %s without POST', async kind => {
  const onUpload = vi.fn(); render(<UploadPanel {...props} onUpload={onUpload} />);
  const file = kind === 'unsupported' ? new File(['bad'], 'bad.txt', { type: 'text/plain' }) : video();
  if (kind !== 'unsupported') Object.defineProperty(file, 'size', { value: kind === 'empty' ? 0 : 200 * 1024 * 1024 + 1 });
  fireEvent.change(screen.getByLabelText('Видеофайл'), { target: { files: [file] } });
  await screen.findByRole('alert'); expect(onUpload).not.toHaveBeenCalled();
});
test('disabled panel blocks input', () => {
  render(<UploadPanel {...props} enabled={false} />);
  expect((screen.getByLabelText('Видеофайл') as HTMLInputElement).disabled).toBe(true);
});
test('indeterminate transfer and abort do not claim server cancellation', () => {
  const onAbort = vi.fn(); render(<UploadPanel {...props} uploading onAbort={onAbort} progress={{ loaded: 0, total: 50, computable: false }} />);
  expect(screen.getByRole('progressbar').hasAttribute('value')).toBe(false);
  expect(screen.getByRole('status').textContent).toContain('не отменяет уже принятое');
  fireEvent.click(screen.getByRole('button', { name: 'Прервать передачу' })); expect(onAbort).toHaveBeenCalledOnce();
});
