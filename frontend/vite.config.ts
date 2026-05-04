import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'


// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(
      {
      babel: {
        plugins: [],
      },
    }
    )
  ],
    resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
 
  server: {
    port: 5173,
    host: true, 
    proxy: {
      // In development, Vite proxies /api and /ws to the backend container.
      // "backend" resolves via Docker's internal DNS.
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://backend:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
