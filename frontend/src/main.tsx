import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import './styles.css';
declare const __FIXTURE_MODE__: boolean;
declare const __TEST_API_MODE__: boolean;
const queries = new QueryClient({ defaultOptions: { queries: { staleTime: 0 }, mutations: { retry: false } } });
async function boot() {
  // Vite replaces the constant; production removes this import and its payload.
  const demoOutcome = __FIXTURE_MODE__ ? new URLSearchParams(location.search).get('demo') : null;
  const transport = __FIXTURE_MODE__ ? (await import('./fixtures/contract-fixtures')).createFixtureTransport({ enabled: true, outcome: demoOutcome === 'clean' ? 'no_violation' : demoOutcome === 'error' ? 'failed' : 'violation' }) : undefined;
  createRoot(document.getElementById('root')!).render(<StrictMode><QueryClientProvider client={queries}><App transport={transport} fixtureMode={__FIXTURE_MODE__} apiTestMode={__TEST_API_MODE__} /></QueryClientProvider></StrictMode>);
}
void boot();
