import os
import asyncio
import re
import logging
import httpx
from pathlib import Path
from telegram import Update
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

# Obtener la URL del servidor local (con valor por defecto)
LOCAL_API_URL = os.environ.get("LOCAL_API_URL", "https://api.telegram.org")

# Normalizar la URL para el servidor local
if LOCAL_API_URL != "https://api.telegram.org":
    base_url = LOCAL_API_URL.rstrip('/')
    if not base_url.endswith('/bot'):
        base_url = base_url + '/bot'
    LOCAL_API_BASE = base_url
    logger.info(f"Usando servidor local con base URL: {LOCAL_API_BASE}")
else:
    LOCAL_API_BASE = "https://api.telegram.org"
    logger.info("Usando API oficial de Telegram")

# Cola para procesar archivos secuencialmente
processing_queue = asyncio.Queue()
is_processing = False

# --- Función para verificar el servidor local ---
async def check_local_server(local_url: str) -> bool:
    """Verifica si el servidor local de la API de Telegram está activo y responde."""
    base_url = local_url.rstrip('/')
    endpoints = ["/health", "/ping", "/status", "/"]
    
    for endpoint in endpoints:
        try:
            health_url = f"{base_url}{endpoint}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(health_url)
                if response.is_success or response.status_code in [404, 405]:
                    logger.info(f"✅ Servidor local responde en {health_url} (código {response.status_code})")
                    return True
        except Exception:
            continue
    
    try:
        test_url = f"{base_url}/getMe"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(test_url)
            if response.status_code in [200, 401]:
                logger.info(f"✅ Servidor local responde en {test_url} (código {response.status_code})")
                return True
    except Exception:
        pass
    
    logger.warning(f"⚠️ Servidor local no responde en {base_url}")
    return False

# --- Funciones de Limpieza de Texto ---
def clean_filename(text: str, original_extension: str) -> str:
    """Limpia el texto del comentario para usarlo como nombre de archivo."""
    # 1. Eliminar emojis
    emoji_pattern = re.compile("["
        u"\U0001F600-\U0001F64F"
        u"\U0001F300-\U0001F5FF"
        u"\U0001F680-\U0001F6FF"
        u"\U0001F1E0-\U0001F1FF"
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE)
    text = emoji_pattern.sub(r'', text)

    # 2. Eliminar la parte a partir de un '#'
    if '#' in text:
        text = text.split('#')[0]

    # 3. Eliminar "Sub Español" o "Sub Español."
    text = re.sub(r'Sub Español\.?', '', text, flags=re.IGNORECASE)

    # 4. Reemplazar ':' y '"' por '_'
    text = text.replace(':', '_').replace('"', '_')

    # 5. Limpiar espacios
    text = re.sub(r'\s+', ' ', text).strip()

    # 6. Añadir la extensión original
    if not original_extension.startswith('.'):
        original_extension = f'.{original_extension}'
    
    if not text:
        text = "archivo_sin_nombre"
    
    return f"{text}{original_extension}"

# --- Manejador de Mensajes ---
async def handle_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe el mensaje reenviado y añade los archivos a la cola."""
    global is_processing
    message = update.effective_message

    if not message.document and not message.video:
        await message.reply_text("❌ Por favor, reenvía un archivo de video.")
        return

    caption = message.caption or ""

    file_obj = message.document or message.video
    file_name = file_obj.file_name or "archivo_sin_nombre"
    original_extension = Path(file_name).suffix or ".mp4"

    new_filename = clean_filename(caption, original_extension)

    # Verificar el servidor local (solo si está configurado)
    if LOCAL_API_URL != "https://api.telegram.org":
        logger.info(f"Verificando servidor local en {LOCAL_API_URL}...")
        await message.reply_text("⏳ Despertando servidor local...")
        
        server_ready = await check_local_server(LOCAL_API_URL)
        if not server_ready:
            logger.warning("El servidor local no responde. Intentando de todas formas...")
            await message.reply_text("⚠️ El servidor local no responde. El procesamiento podría fallar.")
        else:
            logger.info("✅ Servidor local verificado y activo.")
            await message.reply_text("✅ Servidor local activo. Procesando archivo...")

    # Añadir el trabajo a la cola
    await processing_queue.put((file_obj, new_filename, update.effective_chat.id, message.message_id))

    if not is_processing:
        is_processing = True
        context.application.create_task(process_queue(context))

    await message.reply_text(f"✅ Archivo añadido a la cola.\n📝 Nuevo nombre: `{new_filename}`", parse_mode='Markdown')

# --- Procesador de la Cola ---
async def process_queue(context: ContextTypes.DEFAULT_TYPE):
    """Procesa los archivos de la cola uno por uno."""
    global is_processing
    bot = context.bot

    while not processing_queue.empty():
        file_obj, new_filename, chat_id, reply_to_msg_id = await processing_queue.get()

        try:
            # Obtener el archivo (solo para tener el file_id, sin descargar)
            file = await bot.get_file(file_obj.file_id, read_timeout=120.0, write_timeout=120.0)
            
            # Enviar como documento usando el file_id y forzando el nuevo nombre
            # disable_content_type_detection=True evita que Telegram lo detecte como video
            await bot.send_document(
                chat_id=chat_id,
                document=file.file_id,               # Usar el file_id directamente
                filename=new_filename,               # Nombre deseado
                reply_to_message_id=reply_to_msg_id,
                disable_content_type_detection=True, # FORZAR DOCUMENTO
                read_timeout=120.0,
                write_timeout=120.0,
                connect_timeout=60.0
            )
            
            await bot.send_message(
                chat_id,
                f"✅ Archivo enviado correctamente como DOCUMENTO:\n`{new_filename}`",
                parse_mode='Markdown'
            )
            logger.info(f"✅ Archivo procesado: {new_filename}")

        except Exception as e:
            error_msg = f"❌ Error al procesar el archivo: {str(e)}"
            await bot.send_message(chat_id, error_msg)
            logger.error(f"❌ Error procesando archivo: {e}")

        await asyncio.sleep(1)

    is_processing = False
    logger.info("📭 Cola de procesamiento vacía")

# --- Comandos ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 ¡Hola! Soy un bot para renombrar archivos de video.\n\n"
        "📤 **Cómo usar:**\n"
        "1. Reenvía un archivo de video a este chat.\n"
        "2. Asegúrate de que el comentario tenga el nombre deseado.\n"
        "3. El bot limpiará el nombre y te devolverá el archivo como DOCUMENTO.\n\n"
        "📝 **Ejemplo de comentario:**\n"
        "`✅ Toumei na Yoru ni Kakeru Kimi to, Me ni Mienai Koi wo Shita.`\n"
        "`⚡️ Episodio 2 Sub Español.`\n"
        "`#Toumei_na_Yoru_ni_Kakeru_Kimito...`\n\n"
        "Esto resultará en:\n"
        "`Toumei na Yoru ni Kakeru Kimi to, Me ni Mienai Koi wo Shita. Episodio 2.mp4`",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 **Ayuda:**\n\n"
        "1. Reenvía un archivo de video.\n"
        "2. El archivo se renombrará según el comentario.\n"
        "3. Los archivos se procesan en cola (uno tras otro).\n\n"
        "🔧 **Limpieza automática:**\n"
        "- Elimina emojis y caracteres especiales.\n"
        "- Elimina '#hashtags' y 'Sub Español'.\n"
        "- Reemplaza ':' y '\"' por '_'.",
        parse_mode='Markdown'
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    queue_size = processing_queue.qsize()
    status = "🟢 Procesando..." if is_processing else "🟡 En espera"
    await update.message.reply_text(
        f"📊 **Estado del bot:**\n"
        f"- Cola: {queue_size} archivos pendientes\n"
        f"- Estado: {status}\n"
        f"- API URL: {LOCAL_API_URL}",
        parse_mode='Markdown'
    )

# --- Función Principal ---
def main():
    """Inicia el bot."""
    application = Application.builder() \
        .base_url(LOCAL_API_BASE) \
        .token(TOKEN) \
        .build()

    # Manejadores de comandos
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats))

    # Manejador de mensajes
    application.add_handler(MessageHandler(
        filters.FORWARDED & (filters.Document.VIDEO | filters.VIDEO),
        handle_forward
    ))
    application.add_handler(MessageHandler(
        filters.Document.VIDEO | filters.VIDEO,
        handle_forward
    ))

    logger.info("🤖 Bot iniciado correctamente")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
