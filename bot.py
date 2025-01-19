from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    filters,
    ConversationHandler,
    PicklePersistence,
)
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
import os
from pickle import load
import chatlas
from dotenv import load_dotenv

load_dotenv()

BACKENDS = {
    "Anthropic (Claude)": chatlas.ChatAnthropic,
    "GitHub model marketplace": chatlas.ChatGithub,
    "Google (Gemini)": chatlas.ChatGoogle,
    "Groq": chatlas.ChatGroq,
    "OpenAI": chatlas.ChatOpenAI,
    "perplexity.ai": chatlas.ChatPerplexity,
}


def main():
    builder = Application.builder()
    builder.token(os.getenv("telegram_access_token"))
    builder.persistence(persistence=PicklePersistence(filepath="storage.pkl"))
    app = builder.build()
    app.add_handler(CommandHandler("start", start))
    add_registraion(app)
    app.add_handler(CommandHandler("disconnect", forget_everything))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    print("Start polling ...")
    restart_jobs(app)
    app.run_polling()


async def chat(update, context):
    await update.message.reply_chat_action("typing")
    client = context.user_data.get("client")
    response = get_reply(client=client, text=update.message.text)
    await update.message.reply_markdown(response)


def get_reply(client, text):
    return str(client.chat(text, echo="none"))


def add_registraion(app):
    registration = ConversationHandler(
        entry_points=[CommandHandler("connect", start_registration)],
        states={
            0: [MessageHandler(filters.Text(BACKENDS.keys()), ask_for_credentials)],
            1: [MessageHandler(filters.TEXT, save_credentials)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(registration)


async def start_registration(update, context):
    client = context.user_data.get("client")
    backend_kwargs = context.user_data.get("backend_kwargs")
    if (client is None) or (backend_kwargs is None):
        await update.message.reply_text(
            "Please select an LLM Provider",
            reply_markup=ReplyKeyboardMarkup([[b] for b in BACKENDS.keys()]),
        )
        context.user_data["backend_kwargs"] = dict()
        return 0
    else:
        message = "You are already connected to an LLM. Please /disconnect first."
        await update.message.reply_text(message)
        return ConversationHandler.END


async def ask_for_credentials(update, context):
    backend = update.message.text
    if backend not in BACKENDS.keys():
        await update.message.reply_text(
            "Invalid response, canceling.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END
    else:
        context.user_data["backend"] = BACKENDS.get(backend)
        await update.message.reply_text(
            f"Please provide an API key for {backend}.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return 1


async def save_credentials(update, context):
    context.user_data["backend_kwargs"]["api_key"] = update.message.text
    try:
        await create_client(context=context)
    except Exception as e:
        text = e
    else:
        text = "Success! You can start chatting now."
    finally:
        await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END


async def create_client(context):
    backend = context.user_data.get("backend")
    backend_kwargs = context.user_data.get("backend_kwargs")
    client = backend(**backend_kwargs)
    context.user_data["client"] = client


async def start(update, context):
    message = "\n".join(
        [
            "Hello!",
            "These commands will help you get started:",
            "/start - shows this message",
            "/connect - connects an LLM",
            "/disconnect - disconnects an LLM",
        ]
    )
    await update.message.reply_text(message)


async def cancel(update, context):
    await update.message.reply_text(
        "Okay, action was canceled.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def forget_everything(update, context):
    context.user_data.clear()
    await update.message.reply_text("All user data deleted from my memory.")


def restart_jobs(app):
    users = load_user_data()
    for chat_id in users.keys():
        app.job_queue.run_once(
            callback=create_client,
            when=0,  # now
            chat_id=chat_id,
            user_id=chat_id,
            name=f"{chat_id}_start_client",
        )


def load_user_data():
    try:
        with open("storage.pkl", "rb") as file:
            storage = load(file)
        return storage.get("user_data")
    except FileNotFoundError:
        return dict()


if __name__ == "__main__":
    main()
