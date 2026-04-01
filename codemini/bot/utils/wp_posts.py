import os
import logging
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

WP_URL = os.getenv("CODEMINI_WP_URL", "").rstrip("/")
WP_USERNAME = os.getenv("CODEMINI_WP_USERNAME", "")
WP_APP_PASSWORD = os.getenv("CODEMINI_WP_APP_PASSWORD", "")


def _auth():
    return (WP_USERNAME, WP_APP_PASSWORD)


def get_post_titles() -> list[str]:
    if not WP_URL:
        return []
    titles = []
    page = 1
    while True:
        try:
            resp = requests.get(
                f"{WP_URL}/wp-json/wp/v2/posts",
                params={"per_page": 100, "page": page, "status": "publish,future,draft", "_fields": "title"},
                auth=_auth(),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data:
                break
            for post in data:
                title = post.get("title", {}).get("rendered", "")
                if title:
                    titles.append(title.lower())
            if len(data) < 100:
                break
            page += 1
        except Exception as e:
            logging.warning(f"codemini wp_posts: не удалось получить посты: {e}")
            break
    return titles


def get_categories() -> list[dict]:
    if not WP_URL:
        return []
    try:
        resp = requests.get(
            f"{WP_URL}/wp-json/wp/v2/categories",
            params={"per_page": 100, "hide_empty": False},
            auth=_auth(),
            timeout=10,
        )
        resp.raise_for_status()
        return [{"id": c["id"], "name": c["name"]} for c in resp.json()]
    except Exception as e:
        logging.warning(f"codemini wp_posts: не удалось получить категории: {e}")
        return []


def get_or_create_tag(name: str) -> int | None:
    if not WP_URL:
        return None
    try:
        resp = requests.get(
            f"{WP_URL}/wp-json/wp/v2/tags",
            params={"search": name, "per_page": 5},
            auth=_auth(), timeout=10,
        )
        resp.raise_for_status()
        for tag in resp.json():
            if tag["name"].lower() == name.lower():
                return tag["id"]
        resp = requests.post(
            f"{WP_URL}/wp-json/wp/v2/tags",
            auth=_auth(), json={"name": name}, timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("id")
    except Exception as e:
        logging.warning(f"codemini wp_posts: ошибка с тегом '{name}': {e}")
        return None


def publish_post(post_id: int) -> bool:
    if not WP_URL:
        return False
    try:
        resp = requests.post(
            f"{WP_URL}/wp-json/wp/v2/posts/{post_id}",
            auth=_auth(),
            json={"status": "publish"},
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logging.warning(f"codemini wp_posts: не удалось опубликовать пост {post_id}: {e}")
        return False


def create_draft(
    title: str,
    html_content: str,
    category_id: int | None = None,
    tag_names: list[str] | None = None,
    meta_description: str = "",
    focus_keyword: str = "",
    slug: str = "",
    publish_date: str = "",
    featured_media_id: int | None = None,
) -> dict | None:
    if not WP_URL:
        return None
    payload = {
        "title": title,
        "content": html_content,
        "status": "future" if publish_date else "draft",
    }
    if publish_date:
        payload["date"] = publish_date
    if slug:
        payload["slug"] = slug
    if category_id:
        payload["categories"] = [category_id]
    if featured_media_id:
        payload["featured_media"] = featured_media_id

    yoast_meta = {}
    if meta_description:
        yoast_meta["_yoast_wpseo_metadesc"] = meta_description
    if focus_keyword:
        yoast_meta["_yoast_wpseo_focuskw"] = focus_keyword
    if title:
        yoast_meta["_yoast_wpseo_title"] = title
    if yoast_meta:
        payload["meta"] = yoast_meta

    if tag_names:
        tag_ids = [tid for name in tag_names if (tid := get_or_create_tag(name))]
        if tag_ids:
            payload["tags"] = tag_ids

    try:
        resp = requests.post(
            f"{WP_URL}/wp-json/wp/v2/posts",
            auth=_auth(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        result = {"id": data["id"], "link": data.get("link", "")}
        logging.info(f"codemini wp_posts: черновик создан → ID {result['id']}")
        return result
    except Exception as e:
        logging.warning(f"codemini wp_posts: не удалось создать черновик: {e}")
        return None


def get_all_published(per_page: int = 100) -> list[dict]:
    if not WP_URL:
        return []
    import re
    import html
    try:
        resp = requests.get(
            f"{WP_URL}/wp-json/wp/v2/posts",
            params={"status": "publish", "per_page": per_page, "orderby": "date", "order": "desc",
                    "_embed": 1},
            auth=_auth(),
            timeout=15,
        )
        resp.raise_for_status()
        posts = resp.json()
        result = []
        for p in posts:
            raw_excerpt = p.get("excerpt", {}).get("rendered", "")
            # Сначала unescape, потом убираем теги
            excerpt = re.sub(r"<[^>]+>", "", html.unescape(raw_excerpt)).strip()
            excerpt = html.unescape(excerpt)  # двойной unescape на случай двойного кодирования
            # Убираем "[…]", "[&hellip;]", "Читать далее" в конце
            excerpt = re.sub(r"\s*\[[\u2026&][^\]]*\]$|\s*Читать далее.*$", "", excerpt).strip()[:300]
            # Получаем URL featured image из _embedded
            image_url = ""
            embedded = p.get("_embedded", {})
            featured = embedded.get("wp:featuredmedia", [])
            if featured and isinstance(featured, list):
                image_url = featured[0].get("source_url", "")
            result.append({
                "title": html.unescape(p["title"]["rendered"]),
                "link": p["link"],
                "excerpt": excerpt,
                "image_url": image_url,
            })
        return result
    except Exception as e:
        logging.warning(f"codemini wp_posts: get_all_published: {e}")
        return []


def get_published_today() -> list[dict]:
    if not WP_URL:
        return []
    from datetime import date
    today = date.today().isoformat()
    try:
        resp = requests.get(
            f"{WP_URL}/wp-json/wp/v2/posts",
            params={
                "status": "publish",
                "after": f"{today}T00:00:00",
                "before": f"{today}T23:59:59",
                "per_page": 10,
                "_fields": "title,link,date",
            },
            auth=_auth(),
            timeout=15,
        )
        resp.raise_for_status()
        posts = resp.json()
        return [{"title": p["title"]["rendered"], "link": p["link"], "date": p["date"]} for p in posts]
    except Exception as e:
        logging.warning(f"codemini wp_posts: get_published_today: {e}")
        return []
