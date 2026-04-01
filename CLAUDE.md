# CodeMini — AI-агент для codemini.ru

Партнёрский сайт в нише детского IT-образования. Монетизация через САЛИД (CPS/CPL).
Сайт: codemini.ru (WordPress, хостинг Beget).

## Структура проекта

```
codemini/
├── codemini/               # Python-пакет
│   ├── bot/                # Telegram-бот
│   │   ├── main.py         # Точка входа бота
│   │   ├── orchestrator.py # Оркестратор генерации статей
│   │   ├── agents/         # AI-агенты (writer, editor, seo, researcher, image_finder, topic_generator)
│   │   └── utils/          # Утилиты (wp_posts, vk_posts, ok_posts, file_loader)
│   ├── web/                # Веб-интерфейс (Flask)
│   │   ├── app.py          # Flask-приложение (порт 5001)
│   │   └── templates/      # HTML-шаблоны
│   ├── articles/           # Сгенерированные HTML-статьи
│   ├── brief.md            # Бриф проекта (офферы, рубрики, ЦА)
│   ├── content-plan.md     # Контент-план
│   ├── tone-of-voice.md    # Стиль и голос сайта
│   ├── used-topics.txt     # Использованные темы
│   ├── used-images.txt     # Использованные изображения
│   └── posted-vk.txt       # Опубликованные посты ВКонтакте
├── codemini_web_start.bat  # Запуск веб-интерфейса (Windows)
├── requirements.txt        # Python-зависимости
├── .env                    # Переменные окружения (не в git)
└── CLAUDE.md               # Этот файл
```

## Переменные окружения (.env)

```
CODEMINI_TELEGRAM_BOT_TOKEN=  # Токен Telegram-бота (получить у @BotFather)
NOTIFY_CHAT_ID=               # ID Telegram-группы/чата владельца
OPENROUTER_API_KEY=           # API-ключ OpenRouter
CODEMINI_WP_URL=https://codemini.ru
CODEMINI_WP_USERNAME=         # WordPress логин
CODEMINI_WP_APP_PASSWORD=     # WordPress application password
CODEMINI_VK_TOKEN=            # VK API токен
CODEMINI_VK_GROUP_ID=         # ID группы ВКонтакте
UNSPLASH_ACCESS_KEY=          # Unsplash API для поиска изображений
```

## Запуск

### Веб-интерфейс (браузер)
```bash
python -m codemini.web.app
# Открыть: http://localhost:5001
```
Или запустить `codemini_web_start.bat` на Windows.

### Telegram-бот
```bash
python -m codemini.bot.main
```

## Установка зависимостей

```bash
pip install -r requirements.txt
```

## Что умеет агент

- Генерирует SEO-статьи для codemini.ru по контент-плану
- Публикует в WordPress (черновики или сразу на сайт)
- Постит анонсы в VK и Одноклассники
- Ищет изображения через Unsplash
- Работает через Telegram-бот или веб-интерфейс
- Форматы статей: обзор школы, сравнение, гайд, топ-подборка

## Статус

- [ ] Telegram-бот — токен получен, группа ещё не создана
- [x] Веб-интерфейс — готов
- [x] WordPress-интеграция — настроена
- [x] VK-интеграция — настроена

## Связанные проекты

- `astro-agent` — родительский проект (AstroBot для astro-obzor.ru), откуда выделен codemini
