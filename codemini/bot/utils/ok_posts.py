import hashlib
import logging
import requests


OK_API = "https://api.ok.ru/fb.do"


def _sig(params: dict, secret_key: str) -> str:
    """Вычисляет подпись для OK API."""
    sorted_params = "".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hashlib.md5((sorted_params + secret_key).encode()).hexdigest()


def post_to_ok(
    title: str,
    excerpt: str,
    url: str,
    tags: list[str],
    token: str,
    group_id: str,
    app_key: str = "",
    secret_key: str = "",
) -> bool:
    """
    Публикует пост в группу Одноклассников.
    Требует: access_token, group_id, app_key (публичный), secret_key (session secret).
    session_secret = md5(access_token + application_secret_key)
    """
    if not app_key or not secret_key:
        logging.warning("codemini ok_posts: не заданы CODEMINI_OK_APP_KEY / CODEMINI_OK_SECRET_KEY")
        return False

    hashtags = " ".join(f"#{t.replace(' ', '_')}" for t in tags[:5]) if tags else ""
    text = f"{title}\n\n{excerpt}\n\n{url}"
    if hashtags:
        text += f"\n\n{hashtags}"

    # Тип медиа — текст + ссылка
    attachment = {
        "media": [
            {"type": "text", "text": text},
            {"type": "link", "url": url},
        ]
    }
    import json

    params = {
        "application_key": app_key,
        "format": "json",
        "gid": group_id,
        "media": json.dumps(attachment),
        "method": "mediatopic.post",
        "type": "GROUP_THEME",
        "access_token": token,
    }

    # Подпись считается без access_token
    params_for_sig = {k: v for k, v in params.items() if k != "access_token"}
    session_secret = hashlib.md5((token + secret_key).encode()).hexdigest()
    params["sig"] = _sig(params_for_sig, session_secret)

    try:
        resp = requests.post(OK_API, data=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if "error_code" in data:
            logging.warning(f"codemini ok_posts: ошибка OK API — {data}")
            return False
        logging.info(f"codemini ok_posts: пост опубликован — {data}")
        return True
    except Exception as e:
        logging.warning(f"codemini ok_posts: исключение — {e}")
        return False
