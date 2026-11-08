# 🌌 Audit & SaaS Transformation: Anti-Taro 2.0

## 0.1 CHANGELOG: QA услуг + контент-апгрейд (2026-11-08, круг 2)

### QA-сверка всех услуг (субагент) - исправлено
- **[HIGH] Коллизия дедупликации event_id** (main.py vs callbacks.py, один ключ с nx) - в вебхук-режиме глотала все inline-кнопки. Разведены ключи `vk_event:` / `event_answered:`.
- **[HIGH] Двойное списание за Карту Судьбы** - buy списывал 1500/1000, и generate_destiny_card_logic списывал снова. Теперь Карта Судьбы маршрутизируется напрямую в свою логику списания.
- **[HIGH] Синастрия без данных партнера** - переход через global_cut стирал имя/дату партнера, платный разбор шел с пустыми полями. Данные теперь переносятся через переход.
- **[HIGH] "Вечная" Карта Судьбы жила 24 часа** (Redis TTL) - через сутки снова требовала 1500. Теперь хранится в БД (destiny_card_data) + фолбэк из БД в cache.
- Рефанд при сбоях теперь один раз на час (фарм через "Повторить" закрыт), переменные PDF-картинок инициализированы до try (двойной рефанд), VIP теперь реально покрывает Сонник/Хиромантию (как обещает тариф), покупка скина атомарна, квест Клеопатры починен (birth_* не существовали в БД), молчаливый провал покупки получил сообщение, клавиатура "ТРИАЛ ОКОНЧЕН" показывает реальные тарифы, мертвая ветка natal_chart_menu обезврежена, Путеводитель больше не обещает 700 ✨ вместо 50.

### Контент
- **18+ пост-фильтр**: STOP_WORDS теперь проверяют и Готовый текст разборов (json_mode раньше обходил фильтр) - в execute_generation, destiny и тизерах.
- **Аркан 22 = Мир**: родившиеся 22-го больше не получают Шута.
- **Сезонный круг года** (модуль utils/seasonal.py): 8 врат (Имболк, Остара, Белтейн, Лита, Лугнасад, Мабон, Самайн, Йоль) - вплетаются в шёпот звёзд, посты и Карту дня.
- **Персонализация Карты дня**: отсылка к тегам юзера ("Звезды помнят твой запрос...") + врата дня.
- **Стрик**: доп. дар +100 ✨ за каждые 7 дней верности; ежедневный бонус стал атомарным.

### Ежедневные посты
- **CTR-взвешивание рубрик**: средние клики рубрики за 45 дней задают вес (сильные x3); данные post_clicks наконец работают.
- **ТОП постов (30 дней)** - в админ-аналитике.
- **Гейт качества**: клише, структура абзацев, эмодзи-спам; не прошел - перегенерация, иначе отмена.
- **Джиттер ±30 мин** к времени публикации (jitter в CronTrigger).
- **Серийники**: по понедельникам - часть одной из 3 арок по 5 постов ("Неделя Тени", "Аркан за арканом", "Деньги и звёзды").
- **Лимит коммент->ИИ**: 1 разбор/час/юзер (спамер больше не монополизирует 15 RPM).
- **Сторис**: арт поста дублируется в историю сообщества со ссылкой на бота (best-effort, нужно право stories у токена).

### PDF
- **Единый мистический фон**: группы A-D (12 услуг) раньше печатались на сплошных тёмных цветах ("черный фон") - теперь у всех 5 шаблонов одна фоновая иллюстрация с цветным тинтом группы (читаемость сохранена).

### Персоны
- Имена уже искажены по одной букве (Гузиева и т.д.), защита - в оферте: изменений не требуется (решение владельца).

## 0. CHANGELOG: Security & Economy Fixes (2026-11-08)

Полный аудит (6 направлений) и закрытие находок. Подробная SQL-миграция: `database/security_fixes.sql`.

### P0 - закрыто
- **god_mode «лайн голос»**: энергия теперь только для ADMIN_ID и списка близких (`лайн добавить/убрать/список` в админ-чате, Redis-множество `godmode:allowed`). Остальным - загадочный ответ пса.
- **exec_sql (RCE через anon-ключ Supabase)**: EXECUTE отозван у PUBLIC/anon/authenticated, SQL-консоль удалена из админки.
- **RLS `USING (true)` на vk_esoteric_users**: подготовлен Phase B миграции (применять после добавления `SUPABASE_SERVICE_KEY` в Render; бот поддерживает его с этой версии - `database/config.py`).
- **Вебхук ЮKassa**: тело вебхука больше не доверяется - платеж верифицируется через `GET /v3/payments/{id}`; при недоступности API - 503 (ретрай ЮKassa); IP берется из последнего элемента X-Forwarded-For; энергия начисляется из metadata платежа.
- **Накрутка через sync_mobile_progress**: суточный кап 3000 кликов + минимум 2 сек между синками.

### Экономика
- Атомарные списания `spend_user_balance` (RPC) вместо read-modify-write (buy, Карта Судьбы); рефанды через атомарный `add_energy`.
- Анти-replay: платные натальные разделы и Карта Дня нельзя перезапустить старыми кнопками; Оракул больше не фабрикует стейт расклада.
- Hook&Pay: неоплаченный тизер хранится с shortfall в Redis - вебхук вычитает его из начисления; gen_pdf не отдает текст с пометкой is_teaser.
- Пакеты пополнения начисляют энергию из metadata (обещанная сумма = фактическая).
- «Полная Натальная Карта» (key=all из тарифов) активирует вечный пакет, а не 30-дневный транзит.
- Рефанд при сбоях генерации: маркеры ERROR_RPM_LIMIT / ERROR_AI_UNAVAILABLE → возврат энергии; VIP не получает рефанд по прайсу (закрыт фарм).

### Надежность
- FSM-зеркало: `restore_fsm_dispenser` восстанавливает стейты из Redis при старте - ввод email/вопросы переживают рестарт Render.
- Graceful shutdown по SIGTERM (typing-таски, сессии, runner.cleanup).
- Дедупликация MESSAGE_NEW по event_id; защитное окно daily-cron через Redis-ключ.
- 5 блокирующих Pillow/urlopen вызовов обернуты в `asyncio.to_thread` (фризы бота для всех юзеров).
- RPM-лимитер: 1 слот на запрос вместо слота на ретрай; экспоненциальный бэккофф 429; битые модели убраны из ротации; ключ Gemini маскируется в логах.
- `get_all_users` с пагинацией (раньше молча резалось до 1000); таймауты Supabase-сессии 30с; Sentry sample rate 0.2.
- Автопостер: фейл парсинга JSON отменяет пост (раньше сырой ответ ИИ уходил на стену); misfire_grace_time=3600.

### Инфраструктура
- `requirements.txt` (+ apscheduler, чей отсутствие ломало старт), `render.yaml` с установкой Pango (без него PDF молча падал), обновлены README и `.env.example` (правильные UPSTASH_REDIS_REST_*).
- Из корня удалены одноразовые patch_*/fix_* скрипты, test_db/test_sig, дампы profile_*.txt и 56 лог-файлов с vk_id; `.gitignore` закрывает logs/ и *.log.

### Что осталось (сознательно)
- Пассхалка 22 числа -> Шут в Карты Судьбы (продуктовое решение, не трогали).
- Брутфорс скрытых промо (низкий ущерб: 50-200 ✨, кап 10 активаций) - по желанию добавится rate-limit.
- Персоны на реальных людях (юридический риск) - продуктовое решение.

## 1. Technical Audit Summary

### Strengths
*   **Architecture:** Solid hybrid base (Supabase for persistence, Redis for FSM/Locks/Speed).
*   **AI Integration:** Robust Gemini 2.0 implementation with proxy support and key rotation.
*   **Content Engine:** Advanced autoposter with rubrics, viral hooks, and interactive comments.
*   **UI/UX:** Unique "Ghost Interface" (message editing) reduces spam and feels like a native app.
*   **Visuals:** Automated card generation (Pillow) and professional PDF reports.

### Weaknesses (Roadblocks to SaaS)
*   **Scalability:** Hardcoded environment variables (`GROUP_ID`, `VK_TOKEN`) prevent multi-tenancy (White Label).
*   **Data Isolation:** All users are in one table without tenant partitioning.
*   **Resource Intensity:** PDF generation is heavy; needs better queue management for high load.
*   **Mobile Experience:** VK messages are good, but full SaaS potential requires a Web/Mini App interface (partially started in `main.py`).

---

## 2. 20 Ultimate SaaS Improvements

### 🧬 Product & Retention (40%)
1.  **Syndicate Clans:** Collective energy pools and clan-based "Shadow Raids".
2.  **Voice of the Matrix (TTS):** Character voices for insights using ElevenLabs API.
3.  **PvP Matrix Battles:** Card-based duels between users for Energy stakes.
4.  **Cyber-Rituals (Daily Quests):** AI-verified real-world tasks (e.g., photo analysis).
5.  **Proactive Neuro-Navigator:** Predictive alerts based on astrological transits.
6.  **Grimoire Artifacts:** Purchasable "Boosters" (e.g., "Truth Lens" for deeper AI).
7.  **Group Chat Rituals:** Mini-compatible bot for group conversations and compatibility.
8.  **Interactive Destiny Graph:** Visual "Reality Map" in Mini App/PDF showing life sectors.

### 🚀 Marketing & SaaS Business (30%)
9.  **White Label Engine:** Multi-tenant core for selling bot instances to other experts.
10. **Viral "Shadow Mirror":** Style-optimized Pillow cards for wall sharing with deep hooks.
11. **MLM Referral 2.0:** Lifetime commissions on energy purchases for referrers.
12. **Partner API:** Integration for dating/career services to check "System Compatibility".
13. **Influencer Dashboard:** Specialized admin panel for partners to track their traffic.
14. **Oracle Widget:** Embeddable "one-liner" predictor for external websites/blogs.

### ⚙️ Technology & AI Logic (30%)
15. **Deep Context Memory:** Long-term retention of user life events and past "glitches".
16. **Motion PDF (Video Reports):** FFmpeg-driven short video forecasts for Reels/Clips.
17. **User "Bug" Analyzer:** ML-based pattern recognition of user inertia and dropout points.
18. **Cross-platform Bridge:** Unified Supabase profile for VK, Telegram, and Web.
19. **Fine-Tuned Personas (LoRA):** Specialized training for sharper, more cynical ToV.
20. **Real-time Astro Engine:** High-precision ephemeris integration for 100% accurate charts.

---

## 3. Implementation Priorities
1.  **Phase 1:** Multi-tenant Database Refactoring (Foundation for SaaS).
2.  **Phase 2:** Voice Integration (TTS) and Viral Sharing (Marketing & Engagement).
3.  **Phase 3:** Mini App Expansion (UX & Visualization).
