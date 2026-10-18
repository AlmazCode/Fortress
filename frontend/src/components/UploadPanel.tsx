import { useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { MAX_MEDIA_BYTES, MEDIA_LIMITS } from '../api/types';

export function UploadPanel({ onAdd, compact = false }: { onAdd: (files: File[]) => void; compact?: boolean }) {
  const [error, setError] = useState('');
  const dropzone = useDropzone({
    accept: { 'video/mp4': ['.mp4'], 'video/quicktime': ['.mov'] },
    multiple: true, maxSize: MAX_MEDIA_BYTES, minSize: 1,
    onDrop: (files, rejected) => {
      if (files.length) onAdd(files);
      setError(rejected.length ? `Не добавлено файлов: ${rejected.length}. Нужны непустые MP4 или MOV до 200 МиБ.` : '');
    },
  });
  return <section className={`upload-panel ${compact ? 'upload-panel-compact' : ''}`} aria-labelledby={compact ? undefined : 'upload-title'} aria-label={compact ? 'Добавить ещё видео' : undefined}>
    {!compact && <h2 id="upload-title">Добавить видео</h2>}
    <div {...dropzone.getRootProps({ className: `dropzone ${dropzone.isDragActive ? 'drag-active' : ''}`, 'aria-label': 'Выбрать или перетащить видео', role: 'button' })}>
      <input {...dropzone.getInputProps({ 'aria-label': 'Видеофайлы' })} />
      <div className="upload-icon" aria-hidden="true"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 16V4m-4 4 4-4 4 4M4 15v5h16v-5" /></svg></div>
      <strong>{compact ? 'Добавить ещё видео' : 'Перетащите видео сюда'}</strong>
      {!compact && <span>Выберите несколько файлов или вставьте из буфера</span>}
    </div>
    {compact ? <details><summary>Ограничения файла</summary><p className="limits">{MEDIA_LIMITS}</p></details> : <p className="limits">{MEDIA_LIMITS}</p>}
    {error && <p role="alert" className="field-error">{error}</p>}
  </section>;
}
