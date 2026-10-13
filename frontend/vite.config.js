import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const api = process.env.DW_API || 'http://127.0.0.1:8090'
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': api, '/geo': api, '/health': api } },
})
