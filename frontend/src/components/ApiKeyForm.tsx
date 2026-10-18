import { useState, type FormEvent } from 'react';

export function ApiKeyForm({ connected, onConnect, onReset }: { connected: boolean; onConnect: (key: string) => void; onReset: () => void }) {
  const [value, setValue] = useState('');
  function submit(event: FormEvent) { event.preventDefault(); if (!value.trim()) return; onConnect(value.trim()); setValue(''); }
  return <section className="access-panel" aria-labelledby="access-title">
    <h2 id="access-title">Доступ к сервису</h2>
    <p>Ключ хранится только до закрытия или перезагрузки вкладки.</p>
    {connected ? <div className="connected-row"><span><i className="dot green" /> Ключ введён</span><button className="text-button" onClick={onReset}>Сбросить ключ</button></div> : <form onSubmit={submit}>
      <label htmlFor="api-key">API-ключ</label>
      <div className="key-input"><input id="api-key" type="password" value={value} onChange={event => setValue(event.target.value)} autoComplete="off" spellCheck={false} placeholder="Введите ключ доступа" /><button className="primary-button" disabled={!value.trim()} type="submit">Подключить <span aria-hidden="true">↗</span></button></div>
    </form>}
  </section>;
}
