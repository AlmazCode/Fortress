import { useState, type FormEvent } from 'react';
import { Button, StatusBadge } from './ui';

export function ApiKeyForm({ connected, onConnect, onReset }: { connected: boolean; onConnect: (key: string) => void; onReset: () => void }) {
  const [value, setValue] = useState('');
  function submit(event: FormEvent) { event.preventDefault(); if (!value.trim()) return; onConnect(value.trim()); setValue(''); }
  return <section className="access-panel" aria-labelledby="access-title">
    <h2 id="access-title">Доступ к сервису</h2>
    <StatusBadge tone={connected ? 'success' : 'warning'} icon={connected ? 'check' : 'alert'}>{connected ? 'Доступ подключён' : 'Требуется ключ'}</StatusBadge>
    <p className="helper-text">Ключ хранится только до закрытия или перезагрузки вкладки.</p>
    {connected ? <Button variant="text" onClick={onReset}>Сбросить ключ</Button> : <form onSubmit={submit}>
      <label htmlFor="api-key">API-ключ</label>
      <div className="key-input"><input id="api-key" type="password" value={value} onChange={event => setValue(event.target.value)} autoComplete="off" spellCheck={false} placeholder="Введите ключ доступа" /><Button variant="primary" disabled={!value.trim()} type="submit">Подключить</Button></div>
    </form>}
  </section>;
}
