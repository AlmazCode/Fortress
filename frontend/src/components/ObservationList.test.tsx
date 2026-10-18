import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { ObservationList } from './ObservationList';
import type { Observation } from '../api/types';

afterEach(cleanup);
const observation = (): Observation => ({ class_id: 'flat_item_handling', interval: { start_sec: 20, end_sec: 25.5, scene_id: 'local' },
  score: .99, state: 'unreviewed', known_mask: false, visibility: 'unknown', actor_id: null, relations: [] });

test('shows named actions and real intervals without presenting confidence as verified probability', () => {
  const onSeek = vi.fn();
  render(<ObservationList observations={[observation()]} duration={26} onSeek={onSeek} />);
  fireEvent.click(screen.getByRole('button', { name: /20–25.5 секунд/ }));
  expect(onSeek).toHaveBeenCalledExactlyOnceWith(20);
  expect(screen.getByText(/Работа с купюрой/)).toBeTruthy();
  expect(screen.getByText(/требует проверки/)).toBeTruthy();
  expect(screen.queryByText('99%')).toBeNull();
});

test('state context and invalid intervals do not become action alerts', () => {
  const state = { ...observation(), class_id: 'laptop_screen_lit' };
  const invalid = { ...observation(), interval: { ...observation().interval, end_sec: 100 } };
  render(<ObservationList observations={[state, invalid]} duration={26} onSeek={vi.fn()} />);
  expect(screen.getByText('Действия не локализованы.')).toBeTruthy();
  expect(screen.queryByRole('button', { name: /20–100/ })).toBeNull();
  expect(screen.getByText(/Объекты и состояния/)).toBeTruthy();
});
