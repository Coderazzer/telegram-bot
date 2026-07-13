import asyncio
import re
import os
import logging
from pathlib import Path
from telegram import Update, Document, Video
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Configuración de Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Configuración ---
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("No se ha establecido la variable de entorno BOT_TOKEN")

# Cola para procesar archivos secuencialmente
processing_queue = asyncio.Queue()
is_processing = False

# --- Funciones de Limpieza de Texto ---
def clean_filename(text: str, original_extension: str) -> str:
    """
    Limpia el texto del comentario para usarlo como nombre de archivo.
    - Elimina emojis.
    - Elimina la parte que empieza por '#'.
    - Elimina "Sub Español" y variantes.
    - Reemplaza ':' y '"' por '_'.
    """
    # 1. Eliminar emojis (rangos Unicode comunes)
    emoji_pattern = re.compile("["
        u"\U0001F600-\U0001F64F"  # emoticonos
        u"\U0001F300-\U0001F5FF"  # símbolos y pictogramas
        u"\U0001F680-\U0001F6FF"  # transporte y mapas
        u"\U0001F1E0-\U0001F1FF"  # banderas
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE)
    text = emoji_pattern.sub(r'', text)

    # 2. Eliminar la parte a partir de un '#'
    if '#' in text:
        text = text.split('#')[0]

    # 3. Eliminar "Sub Español" o "Sub Español." (insensible a mayúsculas)
    text = re.sub(r'Sub Español\.?', '', text, flags=re.IGNORECASE)

    # 4. Reemplazar ':' y '"' por '_'
    text = text.replace(':', '_').replace('"', '_')

    # 5. Limpiar espacios múltiples y espacios al inicio/final
    text = re.sub(r'\s+', ' ', text).strip()

    # 6. Añadir la extensión original
    if not original_extension.startswith('.'):
        original_extension = f'.{original_extension}'
    
    # Si el texto queda vacío, usar nombre por defecto
    if not text:
        text = "archivo_sin_nombre"
    
    return f"{text}{original_extension}"

# --- Manejador de Mensajes (Reenvío) ---
async def handle_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe el mensaje reenviado y añade los archivos a la cola."""
    global is_processing
    message = update.effective_message

    # Verificar si el mensaje tiene un documento o un video
    if not message.document and not message.video:
        await message.reply_text(
            "❌ Por favor, reenvía un archivo de video (o un documento que sea un video)."
        )
        return

    # Obtener el comentario (caption) del mensaje reenviado
    caption = message.caption or ""

    # Verificar si el mensaje es un reenvío
    if not message.forward_origin and not message.reply_to_message:
        await message.reply_text(
            "❌ Por favor, usa la función de reenviar de Telegram (no copies y pegues)."
        )
        return

    # Obtener el archivo y su extensión
    file_obj = message.document or message.video
    file_name = file_obj.file_name or "archivo_sin_nombre"
    original_extension = Path(file_name).suffix or ".mp4"  # Asume .mp4 si no tiene

    # Crear el nuevo nombre usando la función de limpieza
    new_filename = clean_filename(caption, original_extension)

    # Añadir el trabajo a la cola
    await processing_queue.put((file_obj, new_filename, update.effective_chat.id, message.message_id))

    if not is_processing:
        is_processing = True
        context.application.create_task(process_queue(context))

    await message.reply_text(f"✅ Archivo añadido a la cola de procesamiento.\n📝 Nuevo nombre: `{new_filename}`", parse_mode='Markdown')

# --- Procesador de la Cola ---
async def process_queue(context: ContextTypes.DEFAULT_TYPE):
    """Procesa los archivos de la cola uno por uno."""
    global is_processing
    bot = context.bot

    while not processing_queue.empty():
        file_obj, new_filename, chat_id, reply_to_msg_id = await processing_queue.get()

        try:
            # Obtener el archivo (sin descargarlo completamente)
            file = await bot.get_file(file_obj.file_id)
            
            # Enviar el archivo como documento con el nuevo nombre
            await bot.send_document(
                chat_id=chat_id,
                document=file.file_id,
                filename=new_filename,
                reply_to_message_id=reply_to_msg_id
            )
            await bot.send_message(
                chat_id,
                f"✅ Archivo enviado correctamente como:\n`{new_filename}`",
                parse_mode='Markdown'
            )
            logger.info(f"Archivo procesado: {new_filename}")

        except Exception as e:
            error_msg = f"❌ Error al procesar el archivo: {str(e)}"
            await bot.send_message(chat_id, error_msg)
            logger.error(f"Error procesando archivo: {e}")

        # Pequeña pausa para no saturar la API
        await asyncio.sleep(1)

    is_processing = False
    logger.info("Cola de procesamiento vacía")

# --- Comandos Básicos ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mensaje de bienvenida."""
    await update.message.reply_text(
        "🤖 ¡Hola! Soy un bot para renombrar archivos de video.\n\n"
        "📤 **Cómo usar:**\n"
        "1. Reenvía un archivo de video a este chat.\n"
        "2. Asegúrate de que el comentario tenga el nombre deseado.\n"
        "3. El bot limpiará el nombre y te devolverá el archivo.\n\n"
        "📝 **Ejemplo de comentario:**\n"
        "`✅ Toumei na Yoru ni Kakeru Kimi to, Me ni Mienai Koi wo Shita.`\n"
        "`⚡️ Episodio 2 Sub Español.`\n"
        "`#Toumei_na_Yoru_ni_Kakeru_Kimito...`\n\n"
        "Esto resultará en:\n"
        "`Toumei na Yoru ni Kakeru Kimi to, Me ni Mienai Koi wo Shita. Episodio 2.mp4`",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra ayuda."""
    await update.message.reply_text(
        "📖 **Ayuda:**\n\n"
        "1. Reenvía un archivo de video.\n"
        "2. El archivo se renombrará según el comentario.\n"
        "3. Los archivos se procesan en cola (uno tras otro).\n\n"
        "🔧 **Limpieza automática:**\n"
        "- Elimina emojis y caracteres especiales.\n"
        "- Elimina '#hashtags' y 'Sub Español'.\n"
        "- Reemplaza ':' y '\"' por '_'.\n\n"
        "❓ Si tienes dudas, contacta al administrador.",
        parse_mode='Markdown'
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra estadísticas de la cola."""
    queue_size = processing_queue.qsize()
    status = "🟢 Procesando..." if is_processing else "🟡 En espera"
    await update.message.reply_text(
        f"📊 **Estado del bot:**\n"
        f"- Cola: {queue_size} archivos pendientes\n"
        f"- Estado: {status}",
        parse_mode='Markdown'
    )

# --- Función Principal ---
def main():
    """Inicia el bot."""
    # Crear la aplicación
    application = Application.builder().token(TOKEN).build()

    # Manejadores de comandos
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats))

    # Manejador de mensajes reenviados con archivos
    application.add_handler(MessageHandler(
        filters.FORWARDED & (filters.Document.VIDEO | filters.VIDEO),
        handle_forward
    ))

    # También manejar mensajes con archivos adjuntos directamente (no solo reenvíos)
    application.add_handler(MessageHandler(
        filters.Document.VIDEO | filters.VIDEO,
        handle_forward
    ))

    logger.info("Bot iniciado correctamente")
    
    # Iniciar el bot
    application.run_polling()

if __name__ == "__main__":
    main()
