import { defineConfig } from 'vite'
import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import path from 'path'
import babel from '@rolldown/plugin-babel'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    babel({ presets: [reactCompilerPreset()] })
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
