import { formatTime } from '../api/types';
import type { QueueItem } from '../useVideoQueue';
import { Icon } from './ui';
import type { ReactNode } from 'react';

export function formatBytes(bytes: number): string {
  if (bytes <= 0) return 'Размер не указан';
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} МиБ` : `${Math.max(1, Math.ceil(bytes / 1024))} КиБ`;
}
export function VideoThumbnail({ item }: { item: QueueItem }) {
  return <div className="video-thumbnail">{item.thumbnail ? <img src={item.thumbnail} alt={`Превью ${item.name}`} /> : <Icon name="video" />}<span className="sr-only">{!item.thumbnail && 'Превью недоступно'}</span></div>;
}
export function VideoFile({ item, children }: { item: QueueItem; children?: ReactNode }) {
  return <div className="video-file"><VideoThumbnail item={item} /><div className="video-file-info"><strong title={item.name}>{item.name}</strong>{children}<p>{item.durationSec !== undefined ? formatTime(item.durationSec) : 'Длительность не определена'}<span aria-hidden="true"> · </span>{formatBytes(item.size)}</p></div></div>;
}
