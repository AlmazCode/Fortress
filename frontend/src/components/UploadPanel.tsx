import { useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { MAX_MEDIA_BYTES, MEDIA_LIMITS } from '../api/types';

export function UploadPanel({ onAdd }: { onAdd: (files: File[]) => void }) {
  const [error, setError] = useState('');
  const dropzone = useDropzone({
    accept: { 'video/mp4': ['.mp4'], 'video/quicktime': ['.mov'] },
    multiple: true, maxSize: MAX_MEDIA_BYTES, minSize: 1, noClick: true, noKeyboard: true,
    onDrop: (files, rejected) => {
      if (files.length) onAdd(files);
      setError(rejected.length ? `Не добавлено файлов: ${rejected.length}. Нужны непустые MP4 или MOV до 200 МиБ.` : '');
    },
  });
  return <section className="upload-panel file-picker" aria-label="Выбор видео">
    <div {...dropzone.getRootProps({ className: `file-picker-row ${dropzone.isDragActive ? 'drag-active' : ''}` })}>
      <input {...dropzone.getInputProps({ 'aria-label': 'Видеофайлы' })} />
      <button className="secondary-button" type="button" onClick={event => { event.stopPropagation(); dropzone.open(); }}>Выбрать видео</button>
      <span>Можно выбрать несколько файлов</span>
    </div>
    <p className="limits">{MEDIA_LIMITS}</p>
    {error && <p role="alert" className="field-error">{error}</p>}
  </section>;
}
