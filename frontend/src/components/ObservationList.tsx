import { formatTime, type Observation } from '../api/types';

const names: Record<string, string> = {
  risk_candidate: 'Подозрительный фрагмент по сценарию',
  flat_item_handling: 'Работа с купюрой, карточкой или бумагой',
  counter_interaction: 'Работа с настольным устройством', computer_interaction: 'Работа с компьютером',
  storage_interaction: 'Взаимодействие с сейфом', bag_interaction: 'Работа с сумкой',
  door_interaction: 'Взаимодействие с дверью', writing: 'Запись на бумаге', cup_to_mouth: 'Чашка у лица',
  operator_at_station: 'Оператор у рабочего места', person_at_counter: 'Человек у стойки',
  storage_open: 'Открытая дверца сейфа', safe_open: 'Открытая дверца сейфа', bag_on_desk: 'Сумка на столе',
  laptop_open: 'Открытый ноутбук', laptop_screen_lit: 'Светящийся экран', glass_door_open: 'Открытая дверь',
  two_people_at_counter: 'Два человека у стойки', cup_visible: 'Видимая чашка', garment_on_desk: 'Одежда на столе',
  green_bag_visible: 'Видимая сумка', screen_bright_content: 'Светлое содержимое экрана',
};
const actions = new Set(['risk_candidate', 'flat_item_handling', 'counter_interaction', 'computer_interaction',
  'storage_interaction', 'bag_interaction', 'door_interaction', 'writing', 'cup_to_mouth']);

export function ObservationList({ observations, duration, onSeek }: {
  observations: Observation[]; duration: number; onSeek: (time: number) => void;
}) {
  const valid = observations.filter(o => Number.isFinite(o.interval.start_sec) && Number.isFinite(o.interval.end_sec)
    && o.interval.start_sec >= 0 && o.interval.end_sec >= o.interval.start_sec && o.interval.end_sec <= duration);
  const active = valid.filter(o => actions.has(o.class_id));
  const states = valid.filter(o => !actions.has(o.class_id));
  const row = (observation: Observation, index: number) => <li key={`${observation.class_id}-${index}`}>
    <button className="time-button" onClick={() => onSeek(observation.interval.start_sec)}
      aria-label={`Посмотреть действие: ${names[observation.class_id] ?? observation.class_id}, ${observation.interval.start_sec}–${observation.interval.end_sec} секунд`}>
      {formatTime(observation.interval.start_sec)}–{formatTime(observation.interval.end_sec)} ↗
    </button>{' '}{names[observation.class_id] ?? observation.class_id}
    {observation.state !== 'present' && <span className="muted"> · требует проверки</span>}
  </li>;
  return <section className="coverage-panel" aria-label="Действия на видео">
    <h3>Действия на видео · {active.length}</h3>
    <p className="muted">Предположения модели о действиях и состояниях. Обычное действие не означает нарушение. Нажмите время для просмотра фрагмента.</p>
    {active.length ? <ul>{active.map(row)}</ul> : <p>Действия не локализованы.</p>}
    {states.length > 0 && <details><summary>Объекты и состояния · {states.length}</summary><ul>{states.map(row)}</ul></details>}
  </section>;
}
