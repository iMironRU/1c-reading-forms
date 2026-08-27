# QUICKSTART — развёртывание проекта

Этот файл — для первого запуска. После того как всё развернёшь, можно его удалить (или оставить в `docs/` для истории).

---

## 1. Распаковка

```bash
unzip 1c-reading-forms.zip
cd 1c-reading-forms
```

Внутри уже инициализирован git с первым коммитом «Initial project skeleton». Не нужно делать `git init` заново.

## 2. Создание репозитория на GitHub

```bash
# Создай пустой репозиторий на GitHub: 1c-reading-forms
# Затем:
git remote add origin git@github.com:iMironRU/1c-reading-forms.git
git branch -M main
git push -u origin main
```

## 3. Раскомментировать ссылки на репозиторий

В `mkdocs.yml` сейчас закомментированы строки с `site_url`, `repo_url`, `repo_name`, `edit_uri`. Раскомментируй их после создания репозитория на GitHub:

```yaml
site_url: https://imironru.github.io/1c-reading-forms/
repo_url: https://github.com/iMironRU/1c-reading-forms
repo_name: iMironRU/1c-reading-forms
edit_uri: edit/main/chapters/
```

## 4. Настройка API-ключей для рецензирования

```bash
cp .env.example .env
# Открыть .env и вставить ключи:
#   DEEPSEEK_API_KEY=...
#   OPENAI_API_KEY=...   (опционально, для gpt-4.1)
```

Файл `.env` уже в `.gitignore`, ключи в репозиторий не попадут.

## 5. Проверка скриптов

```bash
chmod +x scripts/*.sh
./scripts/status.sh         # таблица статусов (пока пусто)
```

## 6. Локальный просмотр сайта документации (опционально)

```bash
pip install mkdocs-material
mkdocs serve
# открыть http://127.0.0.1:8000
```

## 7. Включить GitHub Pages (опционально)

GitHub → Settings → Pages → Source: GitHub Actions. После первого пуша в `main` workflow `pages.yml` сам опубликует сайт.

## 8. Запуск сборки книги (форматы EPUB, PDF, DOCX и т.д.)

Автоматически — каждый день в 02:00 UTC по cron из `build.yml`.

Вручную:
```
GitHub → Actions → Build Books → Run workflow
```

Готовые файлы появляются в разделе Releases репозитория.

---

## Структура проекта (напоминание)

```
1c-reading-forms/
├── README.md              — публичное описание
├── CLAUDE.md              — рабочие соглашения (для Claude Code)
├── QUICKSTART.md          — этот файл
├── metadata.yaml          — заголовок, автор, формат
├── mkdocs.yml             — навигация сайта
├── .env.example           — шаблон API-ключей
├── .gitignore
├── .github/workflows/     — GitHub Actions (build, pages)
├── assets/img/            — обложка (TODO: добавить cover.png)
├── chapters/
│   ├── index.md           — главная сайта
│   ├── 00_vvedenie/       — § 0.1 готов, § 0.2 готов
│   └── 01–10/             — пустые папки модулей (с .gitkeep)
├── docs/
│   ├── plan.md            — короткий план/статус
│   └── 00_plan_knigi.md   — полный план (v3)
└── scripts/
    ├── review.sh          — рецензия параграфа (DeepSeek/OpenAI)
    ├── status.sh          — таблица статусов
    └── prompts/reviewer.md — промпт рецензента для книги 3
```

## Следующий шаг

§ 0.3 «Форма как единица интерфейса: разговор о *чём-то одном*» — центральная метафора книги. Открывай Claude Code в этой папке и продолжай.

При старте новой беседы прикрепи:
- `CLAUDE.md`
- `docs/00_plan_knigi.md`
- последний написанный параграф (`chapters/00_vvedenie/00-02_interfeys_polzovatelya.md`)
