import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Production (Salad): served by main.py StaticFiles mount at /interview/
export default defineConfig(({ mode }) => ({
  base: mode === 'production' ? '/interview/' : '/',
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/ws': { target: 'http://127.0.0.1:8000', ws: true },
      '/api': { target: 'http://127.0.0.1:8000' },
      '/static': { target: 'http://127.0.0.1:8000' },
      '/health': { target: 'http://127.0.0.1:8000' },
      '/bot': { target: 'http://127.0.0.1:8000' },
    },
  },
}))
