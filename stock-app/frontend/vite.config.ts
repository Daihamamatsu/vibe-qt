import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

// バックエンド（Django/DRF）のプロキシ設定
// - ローカル開発時は Django 開発サーバーまたは Docker Compose の backend（ホスト 8000 番ポート）
// - バックエンドの URL は /api/... 始まりのため、ここではプレフィックスを除去しない
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
