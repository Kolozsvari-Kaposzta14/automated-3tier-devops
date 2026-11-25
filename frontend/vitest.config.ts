import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Isolated DOM tests require neither a running backend nor PostgreSQL.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    globals: true,
    include: ['tests/**/*.test.tsx'],
  },
});
