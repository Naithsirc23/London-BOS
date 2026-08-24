# Vercel deployment

La PWA se publica desde esta carpeta como frontend Vite estático.

## Configuración del proyecto

- **Root Directory:** `dashboard`
- **Framework Preset:** Vite
- **Install Command:** `pnpm install --frozen-lockfile`
- **Build Command:** `pnpm build:client`
- **Output Directory:** `dist/public`

## Variables de entorno

Para la primera publicación, dejar `VITE_LONDON_BOS_API_URL` vacía. La aplicación mostrará el modo demo de forma explícita.

Solo después de configurar un canal privado y autenticado hacia la API local debe añadirse `VITE_LONDON_BOS_API_URL`. Nunca colocar aquí tokens de Telegram, credenciales de IB Gateway, contraseñas ni claves privadas.

## Importante sobre datos reales

Una publicación en Vercel no conecta automáticamente con el computador de Cris. La API sigue ejecutándose en `127.0.0.1:8002` hasta configurar Tailscale o un gateway seguro. No se debe publicar directamente el puerto 8002.
