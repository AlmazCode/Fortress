import { useEffect, useRef, type ReactNode, type RefObject } from 'react';
import { Button } from './ui';

export function SettingsDrawer({ open, onClose, returnFocus, children }: { open: boolean; onClose: () => void; returnFocus: RefObject<HTMLButtonElement | null>; children: ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    if (open && !element.open) element.showModal();
    else if (!open && element.open) { element.close(); returnFocus.current?.focus(); }
  }, [open, returnFocus]);
  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = previous; };
  }, [open]);
  return <dialog ref={dialog} id="analysis-settings" className="settings-drawer" aria-labelledby="settings-title" onCancel={event => { event.preventDefault(); onClose(); }} onClose={onClose} onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="settings-header"><div><h2 id="settings-title">Настройки</h2><p>Доступ, модель и поиск задания</p></div><Button icon="close" aria-label="Закрыть настройки" onClick={onClose} /></div>
    <div className="settings-content">{children}</div>
  </dialog>;
}
