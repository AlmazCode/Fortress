import type { ComponentProps, ReactNode } from 'react';

const paths = {
  upload: <><path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5" /></>,
  video: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m10 9 5 3-5 3Z" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  check: <><circle cx="12" cy="12" r="9" /><path d="m8 12 3 3 5-6" /></>,
  alert: <><path d="m12 3 10 18H2Z" /><path d="M12 9v4m0 4h.01" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6m0-10h.01" /></>,
  settings: <><path d="m9 3-1 3-3 1-2 5 2 5 3 1 1 3h6l1-3 3-1 2-5-2-5-3-1-1-3Z" /><circle cx="12" cy="12" r="3" /></>,
  trash: <><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7" /></>,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  play: <path d="m8 4 12 8-12 8Z" />,
  pause: <><path d="M8 4v16M16 4v16" /></>,
  arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
  loader: <path d="M21 12a9 9 0 1 1-6-8.5" />,
} satisfies Record<string, ReactNode>;
export type IconName = keyof typeof paths;
export function Icon({ name, className = '' }: { name: IconName; className?: string }) {
  return <svg className={`ui-icon ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">{paths[name]}</svg>;
}
export function Button({ variant = 'secondary', icon, className = '', children, ...props }: ComponentProps<'button'> & { variant?: 'primary' | 'secondary' | 'text'; icon?: IconName }) {
  return <button type="button" {...props} className={`ui-button ${variant}-button ${className}`}>{icon && <Icon name={icon} />}{children}</button>;
}
export function StatusBadge({ tone = 'neutral', icon = 'clock', children }: { tone?: 'neutral' | 'active' | 'success' | 'danger' | 'warning'; icon?: IconName; children: ReactNode }) {
  return <span className={`status-badge status-${tone}`}><Icon name={icon} className={icon === 'loader' ? 'icon-spin' : ''} />{children}</span>;
}
export function Notification({ tone = 'info', children, className = '', role = 'status' }: { tone?: 'info' | 'warning' | 'danger'; children: ReactNode; className?: string; role?: 'status' | 'alert' | 'note' }) {
  return <div className={`notification notification-${tone} ${className}`} role={role}><Icon name={tone === 'info' ? 'info' : 'alert'} /><div>{children}</div></div>;
}
