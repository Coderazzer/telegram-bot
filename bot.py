import os
import asyncio
import re
import logging
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("No se ha establecido BOT_TOKEN")

# Usar API oficial (eliminar LOCAL_API_URL o dejarlo como https://api.telegram.org)
processing_queue = asyncio.Queue()
is_processing = False

def clean_filename(text: str, original_extension: str) -> str:
    emoji_pattern = re.compile("["
        u"\U0001F600-\U0001F64F"
        u"\U0001F300-\U0001F5FF"
        u"\U0001F680-\U0001F6FF"
        u"\U0001F1E0-\U0001F1FF"
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE)
    text = emoji_pattern.sub(r'', text)
    if '#' in text:
        text = text.split('#')[0]
    text = re.sub(r'Sub Español\.?', '', text, flags=re.IGNORECASE)
    text = text.replace(':', '_').replace('"', '_')
    text = re.sub(r'\s+', ' ', text).strip()
    if not original_extension.startswith('.'):
        original_extension = f'.{original_extension}'
    return f"{text or 'archivo_sin_nombre'}{original_extension}"

async def handle_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_processing
    message = update.effective_message
    if not message.document and not message.video:
        await message.reply_text("❌ Reenvía un archivo de video.")
        return
    caption = message.caption or ""
    file_obj = message.document or message.video
    file_name = file_obj.file_name or "archivo_sin_nombre"
    original_extension = Path(file_name).suffix or ".mp4"
    new_filename = clean_filename(caption, original_extension)
    await processing_queue.put((file_obj, new_filename, update.effective_chat.id, message.message_id))
    if not is_processing:
        is_processing = True
        context.application.create_task(process_queue(context))
    await message.reply_text(f"✅ Archivo añadido a la cola.\n📝 Nuevo nombre: `{new_filename}`", parse_mode='Markdown')

async def process_queue(context: ContextTypes.DEFAULT_TYPE):
    global is_processing
    bot = context.bot
    while not processing_queue.empty():
        file_obj, new_filename, chat_id, reply_to_msg_id = await processing_queue.get()
        try:
            file = await bot.get_file(file_obj.file_id)
            await bot.send_document(
                chat_id=chat_id,
                document=file.file_id,
                filename=new_filename,
                reply_to_message_id=reply_to_msg_id,
                disable_content_type_detection=True  # Forzar documento
            )
            await bot.send_message(chat_id, f"✅ Archivo enviado como documento:\n`{new_filename}`", parse_mode='Markdown')
            logger.info(f"Procesado: {new_filename}")
        except Exception as e:
            await bot.send_message(chat_id, f"❌ Error: {str(e)}")
            logger.error(f"Error: {e}")
        await asyncio.sleep(1)
    is_processing = False
    logger.info("Cola vacía")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Bot renombrador de videos.\n"
        "Reenvía un video con un comentario y lo devolveré con el nombre limpio.\n"
        "⚠️ Límite: 50 MB (API oficial)."
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Cola: {processing_queue.qsize()} archivos")

def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(MessageHandler(filters.FORWARDED & (filters.Document.VIDEO | filters.VIDEO), handle_forward))
    application.add_handler(MessageHandler(filters.Document.VIDEO | filters.VIDEO, handle_forward))
    logger.info("Bot iniciado")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
