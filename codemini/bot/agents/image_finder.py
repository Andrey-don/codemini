import json
import logging
import os
import random
import requests
from pathlib import Path
from dotenv import load_dotenv
from bot.utils.openrouter import call_agent
from codemini.bot.utils.wp_media import upload_image_from_url

load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

USED_IMAGES_FILE = Path(__file__).parent.parent.parent / "used-images.txt"


def _load_used_ids() -> set:
    if USED_IMAGES_FILE.exists():
        return set(USED_IMAGES_FILE.read_text(encoding="utf-8").splitlines())
    return set()


def _save_used_id(photo_id: str):
    with open(USED_IMAGES_FILE, "a", encoding="utf-8") as f:
        f.write(photo_id + "\n")

MODEL = "anthropic/claude-haiku-4-5"
TEMPERATURE = 0.2

EXTRACT_PROMPT = """Ты помогаешь подобрать иллюстрации для статьи об онлайн-школах программирования для детей.

Прочитай статью и определи 2-3 места, где уместно вставить изображение.
Для каждого места укажи:
- search_query: поисковый запрос на английском для Unsplash (2-4 слова).
  ВАЖНО: запросы должны быть РАЗНЫМИ и соответствовать теме раздела статьи.
  Примеры хороших запросов по теме:
  - робототехника: "arduino robot kit", "raspberry pi project", "lego robotics children"
  - Scratch: "scratch programming blocks", "game development kids"
  - Python: "python code screen", "programming terminal laptop"
  - сравнение школ: "online learning tablet child", "student e-learning home"
  - выбор курса: "parent child computer", "learning decision education"
  - НЕ используй: "child coding computer", "girl keyboard" — эти уже использованы
- after_heading: точный текст H2-заголовка БЕЗ ## и пробелов по краям, после которого вставить изображение

Верни строго JSON-массив без пояснений и markdown-обёртки:
[
  {"search_query": "arduino robot kit children", "after_heading": "Курсы Arduino для детей"},
  ...
]"""


def search_unsplash_image(query: str, used_ids: set | None = None) -> dict | None:
    access_key = os.getenv("UNSPLASH_ACCESS_KEY", "")
    if not access_key:
        return None
    if used_ids is None:
        used_ids = set()
    try:
        page = random.randint(1, 3)
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "per_page": 10, "orientation": "landscape", "page": page},
            headers={"Authorization": f"Client-ID {access_key}"},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return None
        # Выбираем первое неиспользованное фото
        for photo in results:
            photo_id = photo.get("id", "")
            if photo_id and photo_id in used_ids:
                continue
            url = photo["urls"]["regular"]
            title = photo.get("alt_description") or photo.get("description") or query
            return {"url": url, "title": title.capitalize() if title else query, "id": photo_id}
        # Если все использованы — берём первое
        photo = results[0]
        url = photo["urls"]["regular"]
        title = photo.get("alt_description") or photo.get("description") or query
        return {"url": url, "title": title.capitalize() if title else query, "id": photo.get("id", "")}
    except Exception as e:
        logging.warning(f"codemini image_finder: Unsplash error for '{query}': {e}")
        return None


def insert_image_after_heading(article: str, heading: str, url: str, title: str) -> str:
    heading_md = f"## {heading}"
    if heading_md not in article:
        return article
    image_md = f"\n![{title}]({url})\n"
    return article.replace(heading_md + "\n", heading_md + image_md, 1)


def run(article: str) -> tuple[str, int | None]:
    raw = call_agent(EXTRACT_PROMPT, f"СТАТЬЯ:\n{article}", MODEL, TEMPERATURE)

    try:
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        positions = json.loads(cleaned)
    except Exception as e:
        logging.warning(f"codemini image_finder: не удалось разобрать JSON: {e}")
        return article, None

    result = article
    first_media_id = None
    used_ids = _load_used_ids()

    for pos in positions:
        query = pos.get("search_query", "").strip()
        heading = pos.get("after_heading", "").strip()
        if not query or not heading:
            continue

        image = search_unsplash_image(query, used_ids)
        if not image:
            image = search_unsplash_image("kids programming education", used_ids)

        if image:
            photo_id = image.get("id", "")
            wp_url, media_id = upload_image_from_url(image["url"], image["title"])
            if first_media_id is None and media_id:
                first_media_id = media_id
            if photo_id:
                used_ids.add(photo_id)
                _save_used_id(photo_id)
            final_url = wp_url if wp_url else image["url"]
            result = insert_image_after_heading(result, heading, final_url, image["title"])
            logging.info(f"codemini image_finder: вставлено '{image['title']}' после '{heading}'")
        else:
            logging.warning(f"codemini image_finder: не найдено изображение для '{query}'")

    return result, first_media_id
