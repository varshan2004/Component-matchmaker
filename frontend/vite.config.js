import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/component':    'http://localhost:8000',
      '/alternatives': 'http://localhost:8000',
      '/pricing':      'http://localhost:8000',
      '/health':       'http://localhost:8000',
    }
  }
})