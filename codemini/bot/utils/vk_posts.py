import logging
import requests


VK_API = "https://api.vk.com/method"
VK_VERSION = "5.131"


def _upload_photo_to_vk(image_url: str, token: str, group_id: str) -> str | None:
    """Загружает фото по URL в ВК и возвращает строку вложения вида 'photo{owner}_{id}'."""
    try:
        # 1. Получаем URL для загрузки фото на стену группы
        r = requests.get(f"{VK_API}/photos.getWallUploadServer",
                         params={"access_token": token, "v": VK_VERSION, "group_id": group_id},
                         timeout=10)
        resp_data = r.json()
        if "error" in resp_data:
            logging.warning(f"codemini vk_posts: getWallUploadServer ошибка — {resp_data['error']}")
            return None
        upload_url = resp_data.get("response", {}).get("upload_url")
        if not upload_url:
            logging.warning(f"codemini vk_posts: upload_url не получен — {resp_data}")
            return None

        # 2. Скачиваем картинку
        img_resp = requests.get(image_url, timeout=15)
        img_resp.raise_for_status()

        # 3. Загружаем на сервер ВК
        up = requests.post(upload_url, files={"photo": ("photo.jpg", img_resp.content, "image/jpeg")}, timeout=30)
        up_data = up.json()
        logging.info(f"codemini vk_posts: upload response — {up_data}")
        if "photo" not in up_data or up_data["photo"] == "[]":
            logging.warning(f"codemini vk_posts: фото не загружено — {up_data}")
            return None

        # 4. Сохраняем фото
        save = requests.post(f"{VK_API}/photos.saveWallPhoto",
                             params={"access_token": token, "v": VK_VERSION,
                                     "group_id": group_id,
                                     "server": up_data.get("server"),
                                     "photo": up_data.get("photo"),
                                     "hash": up_data.get("hash")},
                             timeout=10)
        save_data = save.json()
        logging.info(f"codemini vk_posts: saveWallPhoto — {save_data}")
        photos = save_data.get("response", [])
        if photos:
            p = photos[0]
            return f"photo{p['owner_id']}_{p['id']}"
    except Exception as e:
        logging.warning(f"codemini vk_posts: ошибка загрузки фото — {e}")
    return None


def post_to_vk(
    title: str,
    excerpt: str,
    url: str,
    tags: list[str],
    token: str,
    group_id: str,
    image_url: str = "",
) -> bool:
    """
    Публикует пост в группу ВКонтакте.
    group_id — числовой ID группы (без минуса, только цифры).
    """
    hashtags = " ".join(f"#{t.replace(' ', '_')}" for t in tags[:5]) if tags else ""

    lines = [title]
    if excerpt:
        lines.append(excerpt[:300])
    lines.append(url)
    if hashtags:
        lines.append(hashtags)
    message = "\n\n".join(lines)

    # Загружаем фото если есть
    attachments = None
    if image_url:
        attachments = _upload_photo_to_vk(image_url, token, group_id)

    params = {
        "access_token": token,
        "v": VK_VERSION,
        "owner_id": f"-{group_id}",
        "from_group": 1,
        "message": message,
    }
    if attachments:
        params["attachments"] = attachments

    try:
        resp = requests.post(f"{VK_API}/wall.post", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            logging.warning(f"codemini vk_posts: ошибка VK API — {data['error']}")
            return False
        post_id = data.get("response", {}).get("post_id")
        logging.info(f"codemini vk_posts: пост опубликован, ID={post_id}")
        return True
    except Exception as e:
        logging.warning(f"codemini vk_posts: исключение — {e}")
        return False
