import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// F1: browser never talks to :8010 directly — only relative /api/v1 via proxy.
const API_PROXY_TARGET = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8010'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: API_PROXY_TARGET,
        changeOrigin: true,
      },
      '/events': {
        target: API_PROXY_TARGET,
        changeOrigin: true,
      },
      '/health': {
        target: API_PROXY_TARGET,
        changeOrigin: true,
      },
    },
  },
})
