import type { RuleSource as Source } from '../api/types';

const kinds: Record<Source['source_kind'], string> = {
  official: 'Официальный документ', internal_policy: 'Внутренний регламент',
  synthetic: 'Тестовый источник', unverified: 'Непроверенный источник',
};

export function RuleSource({ source }: { source: Source }) {
  const safeLink = source.url && /^https?:\/\//i.test(source.url) ? source.url : undefined;
  return <div className="rule-source">
    <h4>Нормативное основание</h4>
    <dl className="source-fields">
      <div><dt>Документ</dt><dd>{source.title ?? kinds[source.source_kind]}{safeLink && <> · <a href={safeLink} target="_blank" rel="noopener noreferrer">Открыть документ ↗</a></>}{!source.title && <span className="source-missing">Название документа не предоставлено.</span>}</dd></div>
      <div><dt>Статья / пункт</dt><dd>{source.section ?? 'Не указан'}</dd></div>
      <div><dt>Редакция</dt><dd>{source.revision ?? 'Не указана'}</dd></div>
    </dl>
    <p className={`source-verification ${source.verified ? 'verified' : ''}`}>{source.verified ? 'Источник проверен. Применимость проверьте по документу.' : 'Источник не подтверждён — юридический вывод не установлен.'}</p>
    {source.url && !safeLink && <p className="field-error">Ссылка на источник недействительна.</p>}
    {source.limitations.length > 0 && <details><summary>Ограничения источника</summary>{source.limitations.map((line, index) => <p key={index}>{line}</p>)}</details>}
  </div>;
}
