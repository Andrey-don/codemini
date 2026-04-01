from bot.utils.openrouter import call_agent
from codemini.bot.utils.file_loader import read_project_file

MODEL = "anthropic/claude-haiku-4-5"
TEMPERATURE = 0.2

SYSTEM_PROMPT = """Ты — SEO-специалист для партнёрского сайта об онлайн-школах программирования для детей codemini.ru.

Анализируешь статью и выдаёшь строго по пунктам:

1. **Заголовок** — финальный H1 для публикации (до 60 символов, с ключевым словом)
2. **Рубрика** — выбери одну из списка существующих рубрик сайта. Если ни одна не подходит — предложи новую
3. **Метки** — 5-8 тегов через запятую (конкретные термины: название школы, возраст, направление)
4. **Meta Description** — 150-160 символов, с выгодой для родителя
5. **Фокусное слово** — ОДНО главное слово из заголовка (пункт 1): название школы, бренда или ключевой термин. НЕ используй: «Сравнение», «Обзор», «Гайд», «Курсы», «Школа» — только конкретное название
6. **Ключевые слова** — 5-7 поисковых фраз родителей (например: "курсы программирования для детей 8 лет")
7. **Slug** (URL) — латиницей, через дефис, без стоп-слов (например: progkids-obzor)
8. **Замечания** — что исправить для лучшего SEO"""


def run(article: str, categories: list[str] | None = None) -> str:
    brief = read_project_file("brief.md")
    if categories:
        cat_list = "\n".join(f"- {c}" for c in categories)
        categories_block = f"РУБРИКИ В WORDPRESS (выбери строго одну из этого списка, скопируй название ТОЧНО как написано):\n{cat_list}"
    else:
        categories_block = f"РУБРИКИ САЙТА (из brief):\n{brief}"
    context = f"""
СТАТЬЯ:
{article}

{categories_block}

Выдай SEO-данные и выбери рубрику для публикации в WordPress.
"""
    return call_agent(SYSTEM_PROMPT, context, MODEL, TEMPERATURE)
