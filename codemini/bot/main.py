import os
import asyncio
import logging
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters,
)
from telegram.request import HTTPXRequest
from codemini.bot import orchestrator
from codemini.bot.utils import wp_posts
from codemini.bot.utils.file_loader import mark_topic_used

load_dotenv()
logging.basicConfig(level=logging.INFO)

ALLOWED_CHAT_ID = int(os.getenv("NOTIFY_CHAT_ID", "0"))

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["✍️ Написать статью", "📋 План"],
        ["📝 Обзор", "⚖️ Сравнение", "📖 Гайд"],
        ["📅 Запланировать на 10 дней", "🧪 Тест (2 статьи)"],
        ["🔔 Проверить публикацию", "⏹ Стоп"],
        ["🔄 Рестарт"],
    ],
    resize_keyboard=True,
)

BUTTON_TEXTS = {
    "✍️ Написать статью", "📋 План", "📝 Обзор", "⚖️ Сравнение", "📖 Гайд",
    "📅 Запланировать на 10 дней", "🧪 Тест (2 статьи)",
    "🔔 Проверить публикацию", "⏹ Стоп", "🔄 Рестарт",
}

user_state: dict = {}
cancel_flags: dict = {}


def _is_allowed(update: Update) -> bool:
    return update.message.chat_id == ALLOWED_CHAT_ID


async def _notify_unauthorized(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    chat_id = update.message.chat_id
    text = update.message.text or ""
    msg = (
        f"⚠️ Попытка доступа к CodeMini-боту!\n"
        f"ID: {chat_id}\n"
        f"Имя: {user.full_name}\n"
        f"Username: @{user.username or 'нет'}\n"
        f"Сообщение: {text[:100]}"
    )
    await context.bot.send_message(chat_id=ALLOWED_CHAT_ID, text=msg)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        await update.message.reply_text("Доступ запрещён.")
        await _notify_unauthorized(update, context)
        return
    await update.message.reply_text(
        "Привет! Я пишу статьи для codemini.ru.\n\n"
        "Выбери действие или напиши тему:",
        reply_markup=MAIN_KEYBOARD,
    )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Твой chat_id: {update.message.chat_id}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        await update.message.reply_text("Доступ запрещён.")
        await _notify_unauthorized(update, context)
        return
    text = update.message.text
    chat_id = update.message.chat_id
    state_data = user_state.get(chat_id, {})

    if state_data.get("state") == "waiting_week_date" and text not in BUTTON_TEXTS:
        days = state_data.get("days", 10)
        user_state.pop(chat_id)
        mins = days * 3
        await update.message.reply_text(f"Генерирую {days} статей с {text}... ⏳ (~{mins} мин)")
        await _generate_week(update, start_date=text, days=days)
        return

    if state_data.get("state") == "waiting_topic" and text not in BUTTON_TEXTS:
        article_type = state_data["article_type"]
        user_state.pop(chat_id)
        await update.message.reply_text(f"Пишу статью «{text}»... Подожди 1-2 минуты. ⏳")
        try:
            result = await asyncio.to_thread(
                orchestrator.generate_article, topic=text, article_type=article_type
            )
        except Exception as e:
            logging.exception("Ошибка генерации статьи")
            await update.message.reply_text(f"❌ Ошибка при генерации: {e}")
            return
        await _save_draft(update, result)
        return

    if state_data and text in BUTTON_TEXTS:
        user_state.pop(chat_id)

    if text == "✍️ Написать статью":
        user_state[chat_id] = {"state": "waiting_topic", "article_type": "обзор"}
        await update.message.reply_text("Напиши тему статьи:")

    elif text == "📝 Обзор":
        user_state[chat_id] = {"state": "waiting_topic", "article_type": "обзор"}
        await update.message.reply_text("Напиши тему обзора (например: Обзор Progkids):")

    elif text == "⚖️ Сравнение":
        user_state[chat_id] = {"state": "waiting_topic", "article_type": "сравнение"}
        await update.message.reply_text("Напиши тему сравнения (например: Progkids vs Rebotica):")

    elif text == "📖 Гайд":
        user_state[chat_id] = {"state": "waiting_topic", "article_type": "гайд"}
        await update.message.reply_text("Напиши тему гайда (например: Как выбрать курс для ребёнка 7 лет):")

    elif text == "📋 План":
        plan = orchestrator.get_plan()
        chunks = [plan[i:i+4000] for i in range(0, len(plan), 4000)]
        for idx, chunk in enumerate(chunks):
            prefix = "📋 Контент-план:\n\n" if idx == 0 else ""
            await update.message.reply_text(f"{prefix}{chunk}")

    elif text == "📅 Запланировать на 10 дней":
        user_state[chat_id] = {"state": "waiting_week_date", "days": 10}
        await update.message.reply_text("С какой даты? (например: 01.04)")

    elif text == "🧪 Тест (2 статьи)":
        user_state[chat_id] = {"state": "waiting_week_date", "days": 2}
        await update.message.reply_text("С какой даты? (например: 01.04)")

    elif text == "⏹ Стоп":
        cancel_flags[chat_id] = True
        await update.message.reply_text("⏹ Останавливаю после текущей статьи...", reply_markup=MAIN_KEYBOARD)

    elif text == "🔔 Проверить публикацию":
        await _check_published(update)

    elif text == "🔄 Рестарт":
        await update.message.reply_text("🔄 Перезапускаю бота... (~5 сек)")
        with open(".codemini_restart_chat_id", "w") as f:
            f.write(str(chat_id))
        import threading
        threading.Thread(target=_delayed_restart, daemon=True).start()
        await asyncio.sleep(1)
        os._exit(0)


async def _save_draft(update: Update, result: dict):
    draft = await asyncio.to_thread(
        wp_posts.create_draft,
        result["title"],
        result["article"],
        result.get("category_id"),
        result.get("tags", []),
        result.get("meta_description", ""),
        result.get("focus_keyword", ""),
        result.get("slug", ""),
        "",
        result.get("featured_media_id"),
    )
    if draft:
        wp_url = os.getenv("CODEMINI_WP_URL", "").rstrip("/")
        edit_link = f"{wp_url}/wp-admin/post.php?post={draft['id']}&action=edit"
        category_name = result.get("category_name", "")
        cat_line = f"📁 Рубрика: {category_name}\n" if category_name else ""
        published = await asyncio.to_thread(wp_posts.publish_post, draft["id"])
        status = "🟢 Опубликовано!" if published else "📝 Черновик"
        await update.message.reply_text(
            f"{status}\n{cat_line}🔗 {edit_link}",
            reply_markup=MAIN_KEYBOARD,
        )
    else:
        await update.message.reply_text("⚠️ Не удалось сохранить черновик в WordPress.")


async def _generate_week(update, start_date: str = "", days: int = 10):
    chat_id = update.message.chat_id
    cancel_flags[chat_id] = False
    schedule = orchestrator.get_schedule_topics(start_date=start_date, days=days)

    for i, item in enumerate(schedule, 1):
        if cancel_flags.get(chat_id):
            await update.message.reply_text("⏹ Генерация остановлена.", reply_markup=MAIN_KEYBOARD)
            return
        topic = item["topic"]
        article_type = item["article_type"]
        pub_date = item["publish_date"]
        pub_day = pub_date[:10]

        await update.message.reply_text(f"[{i}/{len(schedule)}] Пишу: «{topic}» ({pub_day})...")
        await asyncio.to_thread(mark_topic_used, topic)
        try:
            result = await asyncio.to_thread(
                orchestrator.generate_article, topic=topic, article_type=article_type
            )
        except Exception as e:
            logging.exception(f"Ошибка генерации '{topic}'")
            err = str(e)
            if "402" in err or "credits" in err.lower():
                await update.message.reply_text("❌ Недостаточно баланса OpenRouter!")
            else:
                await update.message.reply_text(f"❌ Ошибка [{topic}]: {err[:200]}")
            continue

        draft = await asyncio.to_thread(
            wp_posts.create_draft,
            result["title"], result["article"],
            result.get("category_id"),
            result.get("tags", []),
            result.get("meta_description", ""),
            result.get("focus_keyword", ""),
            result.get("slug", ""),
            pub_date,
            result.get("featured_media_id"),
        )
        if draft:
            wp_url = os.getenv("CODEMINI_WP_URL", "").rstrip("/")
            edit_link = f"{wp_url}/wp-admin/post.php?post={draft['id']}&action=edit"
            cat = result.get("category_name", "")
            await update.message.reply_text(
                f"✅ {pub_day} — «{result['title']}»\n"
                f"{'📁 ' + cat + chr(10) if cat else ''}"
                f"🔗 {edit_link}"
            )
        else:
            await update.message.reply_text(f"⚠️ Не сохранилась: {topic}")

    days_word = "день" if days == 1 else "дня" if 2 <= days <= 4 else "дней"
    await update.message.reply_text(
        f"🎉 {days} {days_word} готовы! Все статьи запланированы в WordPress.",
        reply_markup=MAIN_KEYBOARD,
    )


async def _check_published(update: Update):
    posts = await asyncio.to_thread(wp_posts.get_published_today)
    if posts:
        from datetime import date
        today = date.today().strftime("%d.%m.%Y")
        lines = "\n\n".join(
            f"📰 «{p['title']}»\n🔗 {p['link']}\n🕙 {p['date'][11:16]}"
            for p in posts
        )
        await update.message.reply_text(
            f"✅ Сегодня {today} опубликовано {len(posts)} статья(-и):\n\n{lines}",
            reply_markup=MAIN_KEYBOARD,
        )
    else:
        from datetime import date
        today = date.today().strftime("%d.%m.%Y")
        await update.message.reply_text(
            f"ℹ️ Сегодня {today} публикаций не было.",
            reply_markup=MAIN_KEYBOARD,
        )


async def _scheduled_check(context):
    chat_id = context.job.data
    posts = await asyncio.to_thread(wp_posts.get_published_today)
    if posts:
        from datetime import date
        today = date.today().strftime("%d.%m.%Y")
        lines = "\n\n".join(
            f"📰 «{p['title']}»\n🔗 {p['link']}\n🕙 {p['date'][11:16]}"
            for p in posts
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ Сегодня {today} опубликовано {len(posts)} статья(-и):\n\n{lines}",
        )
    else:
        from datetime import date
        today = date.today().strftime("%d.%m.%Y")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"ℹ️ Сегодня {today} публикаций не было (проверка 10:15).",
        )


async def on_startup(app):
    chat_id_str = None
    if os.path.exists(".codemini_restart_chat_id"):
        with open(".codemini_restart_chat_id") as f:
            chat_id_str = f.read().strip()
        os.remove(".codemini_restart_chat_id")
        try:
            await app.bot.send_message(
                chat_id=int(chat_id_str),
                text="✅ CodeMini-бот перезапущен!",
                reply_markup=MAIN_KEYBOARD,
            )
        except Exception:
            pass

    notify_chat_id = int(chat_id_str or os.getenv("NOTIFY_CHAT_ID", "0"))
    if notify_chat_id and app.job_queue:
        import datetime
        app.job_queue.run_daily(
            _scheduled_check,
            time=datetime.time(hour=7, minute=15),
            data=notify_chat_id,
            name="codemini_daily_check",
        )


def _delayed_restart():
    import subprocess, sys, time
    time.sleep(4)
    subprocess.Popen([sys.executable, "-m", "codemini.bot.main"])


def main():
    token = os.getenv("CODEMINI_TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("CODEMINI_TELEGRAM_BOT_TOKEN не задан в .env")
    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=60,
        read_timeout=60,
        write_timeout=60,
        pool_timeout=30,
    )
    app = Application.builder().token(token).request(request).post_init(on_startup).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("CodeMini-агент запущен.")
    app.run_polling()


if __name__ == "__main__":
    main()
