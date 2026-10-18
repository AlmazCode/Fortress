import { useImperativeHandle, useState, type Ref } from 'react';
import { useDropzone, type FileRejection } from 'react-dropzone';
import { MAX_MEDIA_BYTES } from '../api/types';
import { Button, Icon, Notification } from './ui';

export interface UploadHandle { open: () => void }
function rejectionText(rejection: FileRejection) {
  const codes = rejection.errors.map(error => error.code);
  if (codes.includes('file-too-large')) return `${rejection.file.name}: файл больше 200 МиБ. Выберите меньший файл.`;
  if (codes.includes('file-too-small')) return `${rejection.file.name}: файл пустой. Выберите непустое видео.`;
  return `${rejection.file.name}: формат не поддерживается. Выберите MP4 или MOV.`;
}
export function UploadPanel({ onAdd, busy = false, controlRef }: { onAdd: (files: File[]) => void; busy?: boolean; controlRef?: Ref<UploadHandle> }) {
  const [errors, setErrors] = useState<string[]>([]);
  const dropzone = useDropzone({
    accept: { 'video/mp4': ['.mp4'], 'video/quicktime': ['.mov'] },
    multiple: true, maxSize: MAX_MEDIA_BYTES, minSize: 1, noClick: true, noKeyboard: true,
    onDrop: (files, rejected) => { if (files.length) onAdd(files); setErrors(rejected.map(rejectionText)); },
  });
  useImperativeHandle(controlRef, () => ({ open: dropzone.open }), [dropzone.open]);
  return <section className="upload-panel" aria-labelledby="upload-title" id="video-upload">
    <h2 id="upload-title">Видео для анализа</h2>
    <div {...dropzone.getRootProps({ className: `upload-zone ${dropzone.isDragActive ? 'drag-active' : ''} ${busy ? 'upload-zone-busy' : ''}` })}>
      <input {...dropzone.getInputProps({ 'aria-label': 'Видеофайлы' })} />
      <span className="upload-symbol"><Icon name="upload" /></span>
      <strong>{dropzone.isDragActive ? 'Отпустите файлы, чтобы добавить их' : 'Перетащите видео сюда'}</strong>
      <span>Можно добавить несколько файлов</span>
      <Button onClick={event => { event.stopPropagation(); dropzone.open(); }}>Выбрать видео</Button>
      <p className="upload-limits">MP4 или MOV · до 200 МиБ · до 180 с</p>
    </div>
    <details className="file-requirements"><summary>Требования к файлам</summary><p>Разрешение — до 1920×1080 или 1080×1920. Частота кадров — до 60 fps. Фактические параметры и возможность декодирования проверяет сервер.</p></details>
    {errors.length > 0 && <Notification tone="danger" role="alert"><strong>Не удалось добавить файлы</strong><ul>{errors.map((error, index) => <li key={index}>{error}</li>)}</ul></Notification>}
  </section>;
}