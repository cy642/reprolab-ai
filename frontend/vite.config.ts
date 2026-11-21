import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
  },
  build: {
    // ECharts 仅在实验分析路由中按需加载。
    chunkSizeWarningLimit: 600,
  },
})
