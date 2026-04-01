import os
import logging
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

WP_URL = os.getenv("CODEMINI_WP_URL", "").rstrip("/")
WP_USERNAME = os.getenv("CODEMINI_WP_USERNAME", "")
WP_APP_PASSWORD = os.getenv("CODEMINI_WP_APP_PASSWORD", "")


def upload_image_from_url(image_url: str, title: str = "") -> str | None:
    if not WP_URL or not WP_USERNAME or not WP_APP_PASSWORD:
        logging.warning("codemini wp_media: WordPress credentials не заданы в .env")
        return None

    try:
        resp = requests.get(image_url, timeout=15)
        resp.raise_for_status()
        image_data = resp.content
        content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
    except Exception as e:
        logging.warning(f"codemini wp_media: не удалось скачать изображение {image_url}: {e}")
        return None

    ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp"}
    ext = ext_map.get(content_type, "jpg")
    safe_title = title[:50].replace(" ", "-").replace("/", "-") if title else "codemini-image"
    filename = f"{safe_title}.{ext}"

    try:
        response = requests.post(
            f"{WP_URL}/wp-json/wp/v2/media",
            auth=(WP_USERNAME, WP_APP_PASSWORD),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": content_type,
            },
            data=image_data,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        wp_url = data.get("source_url")
        media_id = data.get("id")

        # Устанавливаем alt-текст
        if media_id and title:
            try:
                requests.post(
                    f"{WP_URL}/wp-json/wp/v2/media/{media_id}",
                    auth=(WP_USERNAME, WP_APP_PASSWORD),
                    json={"alt_text": title, "title": title, "description": title, "caption": title},
                    timeout=10,
                )
            except Exception:
                pass

        logging.info(f"codemini wp_media: загружено → {wp_url}")
        return wp_url, media_id
    except Exception as e:
        logging.warning(f"codemini wp_media: ошибка загрузки в WordPress: {e}")
        return None, None
