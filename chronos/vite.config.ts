import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base має відповідати назві репозиторію на GitHub — інакше стилі й скрипти
// не завантажаться, коли сайт буде на адресі виду username.github.io/chronos/
export default defineConfig({
  plugins: [react()],
  base: '/chronos/',
})