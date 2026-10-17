import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath } from 'node:url';

export default defineConfig(({ command, mode }) => {
  if (command === 'build' && mode === 'fixture') {
    throw new Error('Synthetic fixtures are for local dev/test only. Use npm run build for production.');
  }
  return {
    plugins: [react(), tailwindcss()],
    define: { __FIXTURE_MODE__: JSON.stringify(mode === 'fixture') },
    server: {
      host: '127.0.0.1',
      fs: { allow: [fileURLToPath(new URL('..', import.meta.url))] },
      proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false } },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      clearMocks: true,
      restoreMocks: true,
    },
  };
});
