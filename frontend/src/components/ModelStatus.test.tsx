import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ModelStatusData } from '../api/types';
import { fixtureCase } from '../fixtures/contract-fixtures';
import { ModelStatus } from './ModelStatus';
afterEach(cleanup);
const model = () => fixtureCase('model_status') as ModelStatusData;
test.each(['missing', 'invalid', 'incompatible', 'test-only'])('unusable %s release is not ready and explains local import', async reason => {
  const value = model(); value.reason = reason; value.test_only = reason === 'test-only'; render(<ModelStatus connected pending={false} model={value} />);
  expect(screen.getByText(/Готовность требует/)).toBeTruthy(); expect(screen.queryByText('Можно начать анализ')).toBeNull();
  const summary = screen.getByText('Как подготовить локальный release'); await userEvent.setup().click(summary); expect(summary.closest('details')?.open).toBe(true);
  expect(screen.getByText(/SHA-256 manifest/)).toBeTruthy();
});
test('only trained validated non-test release can be shown ready', () => {
  const ready = { ...model(), status: 'ready' as const, release_version: 'release-test', reason: null, trained: true, validated: true, test_only: false };
  const view = render(<ModelStatus connected pending={false} model={ready} />); expect(screen.getByText('Можно начать анализ')).toBeTruthy();
  view.rerender(<ModelStatus connected pending={false} model={{ ...ready, trained: false }} />); expect(screen.queryByText('Можно начать анализ')).toBeNull();
});
test('explicit demo remains visibly synthetic even if producer claims ready', () => {
  render(<ModelStatus connected pending={false} fixtureMode model={model()} />); expect(screen.getByText('Synthetic test / demo')).toBeTruthy(); expect(screen.getByText(/реальное качество не проверены/)).toBeTruthy();
});
test.each([360, 768, 1440])('semantic model harness at %spx retains accessible controls', width => {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: width }); render(<ModelStatus connected pending={false} model={model()} />);
  expect(screen.getByRole('region', { name: 'Готовность требует проверки' })).toBeTruthy(); expect(screen.getByText('Как подготовить локальный release').tagName).toBe('SUMMARY');
});
