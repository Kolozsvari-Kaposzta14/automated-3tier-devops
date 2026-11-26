import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The browser calls /api on the Vite origin; Vite forwards requests to FastAPI.
// Production will use the same /api path through Nginx.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
});
