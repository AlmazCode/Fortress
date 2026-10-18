import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ModelStatusData } from '../api/types';
import { fixtureCase } from '../fixtures/contract-fixtures';
import { ModelStatus } from './ModelStatus';
afterEach(cleanup);
const model = () => fixtureCase('model_status') as ModelStatusData;
test.each(['missing', 'invalid', 'incompatible', 'test-only'])('unusable %s release is not ready and explains local import', async reason => {
  const value = model(); value.reason = reason; value.test_only = reason === 'test-only'; render(<ModelStatus connected pending={false} model={value} />);
  expect(screen.getByRole('heading', { name: 'Модель' })).toBeTruthy(); expect(screen.queryByText('Можно начать анализ.')).toBeNull();
  if (value.test_only) expect(screen.getByText('Тестовая модель. Найденные события требуют проверки сотрудником.')).toBeTruthy();
  else {
    const summary = screen.getByText('Как подключить модель'); await userEvent.setup().click(summary); expect(summary.closest('details')?.open).toBe(true);
    expect(screen.getByText(/по инструкции сервера/)).toBeTruthy();
  }
});
test('only trained validated non-test release can be shown ready', () => {
  const ready = { ...model(), status: 'ready' as const, release_version: 'release-test', reason: null, trained: true, validated: true, test_only: false };
  const view = render(<ModelStatus connected pending={false} model={ready} />); expect(screen.getByText('Можно начать анализ.')).toBeTruthy();
  view.rerender(<ModelStatus connected pending={false} model={ready} unavailable />); expect(screen.queryByText('Готова')).toBeNull(); expect(screen.queryByText('Для анализа нужна обученная модель.')).toBeNull();
  view.rerender(<ModelStatus connected pending={false} model={{ ...ready, trained: false }} />); expect(screen.queryByText('Можно начать анализ.')).toBeNull();
});
test('explicit demo remains visibly synthetic even if producer claims ready', () => {
  render(<ModelStatus connected pending={false} fixtureMode model={model()} />); expect(screen.getByText('Тестовая')).toBeTruthy(); expect(screen.getByText('Тестовая модель. Найденные события требуют проверки сотрудником.')).toBeTruthy();
});
test.each([360, 768, 1440])('semantic model harness at %spx retains accessible controls', width => {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: width }); render(<ModelStatus connected pending={false} model={model()} />);
  expect(screen.getByRole('region', { name: 'Модель' })).toBeTruthy(); expect(screen.getByText('Как подключить модель').tagName).toBe('SUMMARY');
});
