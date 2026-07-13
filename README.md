# Telegram Video Renamer Bot

Bot de Telegram que renombra archivos de video según el comentario de la publicación.

## Características

- ✅ Renombra archivos según el comentario del mensaje
- 🔄 Procesamiento en cola (archivos uno tras otro)
- 🧹 Limpieza automática: elimina emojis, hashtags y "Sub Español"
- 📁 Soporta múltiples formatos: .mp4, .mkv, .avi, etc.
- ☁️ Hosting gratuito en Render

## Cómo usar

1. Reenvía un archivo de video al bot
2. Asegúrate de que el comentario tenga el formato deseado
3. El bot te devolverá el archivo con el nombre limpio

## Tecnologías

- Python 3.9+
- python-telegram-bot 20.7
- Asyncio para procesamiento en cola

## Despliegue en Render

1. Fork este repositorio en GitHub
2. Conecta tu repositorio en Render
3. Añade la variable de entorno `BOT_TOKEN`
4. ¡Listo!

## Licencia

MIT