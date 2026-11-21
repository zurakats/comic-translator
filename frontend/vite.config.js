import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendTarget = process.env.VITE_BACKEND_URL || 'http://127.0.0.1:5000'

const proxyConfig = {
  '/api': {
    target: backendTarget,
    changeOrigin: true,
    timeout: 600_000,
    proxyTimeout: 600_000,
    rewrite: (path) => path.replace(/^\/api/, ''),
  },
  '/static': {
    target: backendTarget,
    changeOrigin: true,
    timeout: 600_000,
    proxyTimeout: 600_000,
  },
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: proxyConfig,
  },
  preview: {
    host: true,
    port: 4173,
    proxy: proxyConfig,
  },
})
