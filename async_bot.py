import asyncio
import logging
import os
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route
from telegram import Update
from telegram.ext import Application, ContextTypes, filters, MessageHandler

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Configuration constants
URL = os.environ.get("RENDER_EXTERNAL_URL")
PORT = int(os.environ.get("PORT", 8000))
TOKEN = os.environ.get("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")

USE_WEBHOOK = URL is not None
logger.info("Running in %s mode", "webhook" if USE_WEBHOOK else "polling")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echo the user message."""
    user = update.effective_user
    message = update.message.text if update.message else None
    if not message:
        logger.warning("Received update without text message")
        return
    logger.info("Received message from %s: %s", user.username or user.id, message)
    await update.message.reply_text(message)

async def main() -> None:
    if USE_WEBHOOK:
        logger.info("Starting webhook mode with URL: %s", URL)
        application = Application.builder().token(TOKEN).updater(None).build()
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

        await application.bot.set_webhook(url=f"{URL}/telegram")

        async def telegram(request: Request) -> Response:
            data = await request.json()
            await application.update_queue.put(Update.de_json(data, application.bot))
            return Response()

        async def health(_: Request) -> PlainTextResponse:
            return PlainTextResponse("Bot is running!")

        app = Starlette(routes=[
            Route("/telegram", telegram, methods=["POST"]),
            Route("/healthcheck", health, methods=["GET"]),
        ])

        config = uvicorn.Config(app=app, port=PORT, host="0.0.0.0")
        server = uvicorn.Server(config)

        async with application:
            await application.start()
            await server.serve()
            await application.stop()
    else:
        logger.info("Starting polling mode for local development")
        application = Application.builder().token(TOKEN).build()
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

        async with application:
            await application.start()
            await application.updater.start_polling()
            logger.info("Bot started! Send a message to test it.")

            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                pass
            finally:
                await application.updater.stop()
                await application.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error("Bot failed to start: %s", e)
        raise