import os
import sys
import time
import threading
import queue
import logging
from flask import Flask, render_template, request, Response, stream_with_context
from dotenv import load_dotenv
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)

from codemini.bot import orchestrator
from codemini.bot.utils import wp_posts
from codemini.bot.utils.file_loader import mark_topic_used

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

message_queues: dict[str, queue.Queue] = {}
cancel_flags: dict[str, bool] = {}


def send_msg(session_id: str, text: str):
    if session_id in message_queues:
        message_queues[session_id].put(text)


def _post_to_social(result: dict, wp_link: str):
    """Постинг в соцсети если настроены токены."""
    title = result.get("title", "")
    excerpt = result.get("meta_description", "")
    tags = result.get("tags", [])

    vk_token = os.getenv("CODEMINI_VK_TOKEN")
    vk_group_id = os.getenv("CODEMINI_VK_GROUP_ID")
    ok_token = os.getenv("CODEMINI_OK_TOKEN")
    ok_group_id = os.getenv("CODEMINI_OK_GROUP_ID")

    if vk_token and vk_group_id:
        try:
            from codemini.bot.utils.vk_posts import post_to_vk
            vk_ok = post_to_vk(title, excerpt, wp_link, tags, vk_token, vk_group_id)
            if vk_ok:
                logging.info(f"codemini web: VK пост опубликован — {title}")
        except Exception as e:
            logging.warning(f"codemini web: VK ошибка — {e}")

    if ok_token and ok_group_id:
        try:
            from codemini.bot.utils.ok_posts import post_to_ok
            ok_ok = post_to_ok(title, excerpt, wp_link, tags, ok_token, ok_group_id)
            if ok_ok:
                logging.info(f"codemini web: OK пост опубликован — {title}")
        except Exception as e:
            logging.warning(f"codemini web: OK ошибка — {e}")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/plan")
def plan():
    text = orchestrator.get_plan()
    return {"plan": text}


@app.route("/generate", methods=["POST"])
def generate():
    data = request.json
    topic = data.get("topic", "").strip()
    article_type = data.get("article_type", "обзор")
    session_id = data.get("session_id", "default")
    post_social = data.get("post_social", False)

    if not topic:
        return {"error": "Тема не указана"}, 400

    message_queues[session_id] = queue.Queue()
    cancel_flags[session_id] = False

    def run():
        try:
            send_msg(session_id, f"⏳ Пишу статью «{topic}»... (1-2 минуты)")
            result = orchestrator.generate_article(topic=topic, article_type=article_type)
            draft = wp_posts.create_draft(
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
                wp_posts.publish_post(draft["id"])
                wp_url = os.getenv("CODEMINI_WP_URL", "").rstrip("/")
                edit_link = f"{wp_url}/wp-admin/post.php?post={draft['id']}&action=edit"
                post_link = draft.get("link", "")
                cat = result.get("category_name", "")
                send_msg(session_id, f"✅ Опубликовано: «{result['title']}»")
                if cat:
                    send_msg(session_id, f"📁 {cat}")
                send_msg(session_id, f"🔗 {edit_link}")

                if post_social:
                    send_msg(session_id, "📢 Публикую в соцсети...")
                    _post_to_social(result, post_link or edit_link)
                    vk_ready = bool(os.getenv("CODEMINI_VK_TOKEN") and os.getenv("CODEMINI_VK_GROUP_ID"))
                    ok_ready = bool(os.getenv("CODEMINI_OK_TOKEN") and os.getenv("CODEMINI_OK_GROUP_ID"))
                    if vk_ready:
                        send_msg(session_id, "✅ ВКонтакте — опубликовано")
                    else:
                        send_msg(session_id, "⚠️ ВКонтакте — токен не настроен")
                    if ok_ready:
                        send_msg(session_id, "✅ Одноклассники — опубликовано")
                    else:
                        send_msg(session_id, "⚠️ Одноклассники — токен не настроен")
            else:
                send_msg(session_id, "⚠️ Не удалось сохранить в WordPress")
        except Exception as e:
            logging.exception("Ошибка генерации")
            send_msg(session_id, f"❌ Ошибка: {e}")
        finally:
            send_msg(session_id, "__DONE__")

    threading.Thread(target=run, daemon=True).start()
    return {"status": "started"}


@app.route("/generate_week", methods=["POST"])
def generate_week():
    data = request.json
    start_date = data.get("start_date", "").strip()
    session_id = data.get("session_id", "default")
    days = int(data.get("days", 10))
    post_social = data.get("post_social", False)

    if not start_date:
        return {"error": "Дата не указана"}, 400

    message_queues[session_id] = queue.Queue()
    cancel_flags[session_id] = False

    def run():
        try:
            schedule = orchestrator.get_schedule_topics(start_date=start_date, days=days)
            send_msg(session_id, f"📅 Генерирую {days} статей с {start_date}... (~{days * 3} мин)")
            for i, item in enumerate(schedule, 1):
                if cancel_flags.get(session_id):
                    send_msg(session_id, "⏹ Генерация остановлена.")
                    break
                topic = item["topic"]
                article_type = item["article_type"]
                pub_date = item["publish_date"]
                pub_day = pub_date[:10]

                send_msg(session_id, f"[{i}/{len(schedule)}] Пишу: «{topic}» ({pub_day})...")
                mark_topic_used(topic)
                try:
                    result = orchestrator.generate_article(topic=topic, article_type=article_type)
                except Exception as e:
                    err = str(e)
                    if "402" in err or "credits" in err.lower():
                        send_msg(session_id, "❌ Недостаточно баланса на OpenRouter! Пополни: openrouter.ai/settings/credits")
                    else:
                        send_msg(session_id, f"❌ Ошибка [{topic}]: {err[:200]}")
                    continue

                draft = wp_posts.create_draft(
                    result["title"],
                    result["article"],
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
                    send_msg(session_id, f"✅ {pub_day} — «{result['title']}»")
                    if cat:
                        send_msg(session_id, f"📁 {cat}")
                    send_msg(session_id, f"🔗 {edit_link}")
                else:
                    send_msg(session_id, f"⚠️ Не сохранилась: {topic}")
            else:
                send_msg(session_id, f"🎉 {days} {'день' if days == 1 else 'дня' if 2 <= days <= 4 else 'дней'} готовы! Все статьи запланированы в WordPress.")
        except Exception as e:
            logging.exception("Ошибка планировщика")
            send_msg(session_id, f"❌ Критическая ошибка: {e}")
        finally:
            send_msg(session_id, "__DONE__")

    threading.Thread(target=run, daemon=True).start()
    return {"status": "started"}


@app.route("/stop", methods=["POST"])
def stop():
    data = request.json
    session_id = data.get("session_id", "default")
    cancel_flags[session_id] = True
    return {"status": "stopped"}


@app.route("/check_published", methods=["GET"])
def check_published():
    from datetime import date
    today = date.today()
    posts = wp_posts.get_published_today()
    today_str = today.strftime("%d.%m.%Y")
    return {"today": today_str, "posts": posts}


@app.route("/social_status", methods=["GET"])
def social_status():
    return {
        "vk": bool(os.getenv("CODEMINI_VK_TOKEN") and os.getenv("CODEMINI_VK_GROUP_ID")),
        "ok": bool(os.getenv("CODEMINI_OK_TOKEN") and os.getenv("CODEMINI_OK_GROUP_ID")),
    }


@app.route("/post_social_last", methods=["POST"])
def post_social_last():
    """Публикует последнюю опубликованную запись WordPress в выбранную соцсеть."""
    data = request.json
    network = data.get("network", "vk")

    posts = wp_posts.get_published_today()
    if not posts:
        # Берём последнюю вообще
        try:
            wp_url = os.getenv("CODEMINI_WP_URL", "").rstrip("/")
            import requests as req
            r = req.get(
                f"{wp_url}/wp-json/wp/v2/posts",
                params={"per_page": 1, "status": "publish", "_fields": "title,link,excerpt"},
                timeout=10,
            )
            r.raise_for_status()
            posts_data = r.json()
            if posts_data:
                p = posts_data[0]
                title = p.get("title", {}).get("rendered", "")
                excerpt = p.get("excerpt", {}).get("rendered", "")
                # Убираем HTML-теги из excerpt
                import re
                excerpt = re.sub(r"<[^>]+>", "", excerpt).strip()[:300]
                link = p.get("link", "")
                posts = [{"title": title, "link": link, "excerpt": excerpt}]
        except Exception as e:
            return {"ok": False, "error": f"Не удалось получить посты: {e}"}

    if not posts:
        return {"ok": False, "error": "Нет опубликованных статей"}

    last = posts[0]
    title = last.get("title", "")
    link = last.get("link", "")
    excerpt = last.get("excerpt", last.get("date", ""))[:300]

    if network == "vk":
        token = os.getenv("CODEMINI_VK_TOKEN")
        group_id = os.getenv("CODEMINI_VK_GROUP_ID")
        if not token or not group_id:
            return {"ok": False, "error": "Не настроен CODEMINI_VK_TOKEN или CODEMINI_VK_GROUP_ID в .env"}
        from codemini.bot.utils.vk_posts import post_to_vk
        ok = post_to_vk(title, excerpt, link, [], token, group_id)
        return {"ok": ok, "link": link} if ok else {"ok": False, "error": "Ошибка VK API"}

    elif network == "ok":
        token = os.getenv("CODEMINI_OK_TOKEN")
        group_id = os.getenv("CODEMINI_OK_GROUP_ID")
        app_key = os.getenv("CODEMINI_OK_APP_KEY", "")
        secret_key = os.getenv("CODEMINI_OK_SECRET_KEY", "")
        if not token or not group_id:
            return {"ok": False, "error": "Не настроен CODEMINI_OK_TOKEN или CODEMINI_OK_GROUP_ID в .env"}
        from codemini.bot.utils.ok_posts import post_to_ok
        ok = post_to_ok(title, excerpt, link, [], token, group_id, app_key, secret_key)
        return {"ok": ok, "link": link} if ok else {"ok": False, "error": "Ошибка OK API"}

    return {"ok": False, "error": "Неизвестная сеть"}


@app.route("/post_social_all", methods=["POST"])
def post_social_all():
    """Публикует все статьи WordPress в выбранную соцсеть (с паузой 3 сек между постами)."""
    import time as _time
    data = request.json
    network = data.get("network", "vk")
    session_id = data.get("session_id", "default")

    posts = wp_posts.get_all_published()
    if not posts:
        return {"ok": False, "error": "Нет опубликованных статей"}

    message_queues[session_id] = queue.Queue()

    def run():
        from pathlib import Path as _Path
        posted_file = _Path(__file__).parent.parent / f"posted-{network}.txt"
        posted_urls = set(posted_file.read_text(encoding="utf-8").splitlines()) if posted_file.exists() else set()

        new_posts = [p for p in posts if p.get("link", "") not in posted_urls]
        if not new_posts:
            send_msg(session_id, "✅ Все статьи уже опубликованы в соцсети")
            send_msg(session_id, "__DONE__")
            return

        send_msg(session_id, f"📢 Публикую {len(new_posts)} новых статей в {'ВКонтакте' if network == 'vk' else 'Одноклассники'}...")
        ok_count = 0
        for i, p in enumerate(new_posts, 1):
            title = p.get("title", "")
            link = p.get("link", "")
            excerpt = p.get("excerpt", "")[:300]
            image_url = p.get("image_url", "")
            if network == "vk":
                token = os.getenv("CODEMINI_VK_TOKEN")
                group_id = os.getenv("CODEMINI_VK_GROUP_ID")
                if not token or not group_id:
                    send_msg(session_id, "❌ Нет CODEMINI_VK_TOKEN / VK_GROUP_ID в .env")
                    break
                from codemini.bot.utils.vk_posts import post_to_vk
                ok = post_to_vk(title, excerpt, link, [], token, group_id, image_url)
            elif network == "ok":
                token = os.getenv("CODEMINI_OK_TOKEN")
                group_id = os.getenv("CODEMINI_OK_GROUP_ID")
                app_key = os.getenv("CODEMINI_OK_APP_KEY", "")
                secret_key = os.getenv("CODEMINI_OK_SECRET_KEY", "")
                if not token or not group_id:
                    send_msg(session_id, "❌ Нет CODEMINI_OK_TOKEN / OK_GROUP_ID в .env")
                    break
                from codemini.bot.utils.ok_posts import post_to_ok
                ok = post_to_ok(title, excerpt, link, [], token, group_id, app_key, secret_key)
            else:
                ok = False
            if ok:
                ok_count += 1
                posted_urls.add(link)
                with open(posted_file, "a", encoding="utf-8") as f:
                    f.write(link + "\n")
                send_msg(session_id, f"✅ [{i}/{len(new_posts)}] {title}")
            else:
                send_msg(session_id, f"⚠️ [{i}/{len(new_posts)}] Ошибка: {title}")
            if i < len(posts):
                _time.sleep(3)
        send_msg(session_id, f"🎉 Готово: {ok_count}/{len(new_posts)} опубликовано")
        send_msg(session_id, "__DONE__")

    threading.Thread(target=run, daemon=True).start()
    return {"status": "started"}


@app.route("/restart", methods=["POST"])
def restart():
    import subprocess
    def do_restart():
        time.sleep(1)
        subprocess.Popen([sys.executable, "-m", "codemini.web.app"])
        os._exit(0)
    threading.Thread(target=do_restart, daemon=True).start()
    return {"status": "restarting"}


@app.route("/stream/<session_id>")
def stream(session_id):
    def generate():
        message_queues[session_id] = message_queues.get(session_id, queue.Queue())
        while True:
            try:
                msg = message_queues[session_id].get(timeout=60)
                yield f"data: {msg}\n\n"
                if msg == "__DONE__":
                    break
            except queue.Empty:
                yield "data: __PING__\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


if __name__ == "__main__":
    app.run(debug=False, port=5001, threaded=True)
