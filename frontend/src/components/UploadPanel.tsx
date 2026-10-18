import { useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { MAX_MEDIA_BYTES, MEDIA_LIMITS, type UploadProgress } from '../api/types';

export function UploadPanel({ enabled, uploading, progress, disabledReason, onUpload, onAbort }: { enabled: boolean; uploading: boolean; progress?: UploadProgress; disabledReason?: string; onUpload: (file: File) => void; onAbort: () => void }) {
  const [file, setFile] = useState<File>();
  const [error, setError] = useState('');
  const dropzone = useDropzone({
    accept: { 'video/mp4': ['.mp4'], 'video/quicktime': ['.mov'] },
    maxFiles: 1, maxSize: MAX_MEDIA_BYTES, minSize: 1, disabled: !enabled || uploading,
    onDropAccepted: files => { setFile(files[0]); setError(''); },
    onDropRejected: () => { setFile(undefined); setError('Выберите один непустой MP4 или MOV размером до 200 МиБ.'); },
  });
  const percent = progress?.computable && progress.total > 0 ? Math.min(100, Math.round(100 * progress.loaded / progress.total)) : undefined;
  return <section className="upload-panel" aria-labelledby="upload-title">
    <h2 id="upload-title">Видеозапись</h2>
    <div {...dropzone.getRootProps({ className: `dropzone ${dropzone.isDragActive ? 'drag-active' : ''} ${!enabled ? 'inactive' : ''}`, 'aria-label': 'Выбрать или перетащить видео', role: 'button', 'aria-disabled': !enabled || uploading })}>
      <input {...dropzone.getInputProps({ 'aria-label': 'Видеофайл', disabled: !enabled || uploading })} />
      <div className="upload-icon" aria-hidden="true"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 16V4m-4 4 4-4 4 4M4 15v5h16v-5" /></svg></div>
      <strong>{file ? file.name : 'Перетащите видео сюда'}</strong>
      <span>{file ? `${(file.size / 1024 / 1024).toFixed(1)} МиБ · можно выбрать другой файл` : 'или нажмите, чтобы выбрать файл'}</span>
    </div>
    <p className="limits">{MEDIA_LIMITS}</p>
    {!enabled && !uploading && disabledReason && <p className="muted">{disabledReason}</p>}
    {error && <p role="alert" className="field-error">{error}</p>}
    {uploading && <div className="upload-progress" role="status"><span>Передача файла {percent === undefined ? '…' : `${percent}%`}</span><progress aria-label="Прогресс загрузки" max={100} value={percent} /><p>Прерывание передачи не отменяет уже принятое задание.</p></div>}
    <div className="upload-actions">{uploading ? <button className="secondary-button" onClick={onAbort}>Прервать передачу</button> : <button className="primary-button" onClick={() => file && onUpload(file)} disabled={!enabled || !file}>Начать анализ <span aria-hidden="true">→</span></button>}</div>
  </section>;
}
