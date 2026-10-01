import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: '/tmp/tarot-merged-20260926-bundle',
    emptyOutDir: true,
    rollupOptions: { output: { inlineDynamicImports: true } },
  },
});
