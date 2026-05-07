РАЗДЕЛ 1: ДИНАМИЧЕСКОЕ ОЖИДАНИЕ (UX)
1. Remove long-running loop that sends static text.
   Currently in `modules/tarot.py` (and potentially other places), `send_typing_indicator` runs an infinite loop waiting `asyncio.sleep(5)` and sending "Ожидайте, идет генерация ответа...".
2. Implement `start_dynamic_typing` Utility.
   In `modules/utils.py`, add a utility function `start_dynamic_typing` that accepts `bot_api`, `peer_id`, and `message_id`. It will loop, wait 10s, pick a random phrase from `THEATRICAL_PHRASES`, edit the message, and set "typing" activity.
3. Refactor generation wrappers.
   Update `card_of_day_logic` in `modules/tarot.py` to:
   - Send an initial theatrical phrase immediately, capturing the `message_id`.
   - Start `start_dynamic_typing` task.
   - Call generation API.
   - Cancel the task.
   - Delete the theatrical message before sending the result (or replace it).
4. Apply the same logic in `process_oracle_final` in `modules/tarot.py` and `execute_generation` in `modules/payments.py`.

РАЗДЕЛ 2: ПАМЯТЬ МАТРИЦЫ (AI TAGS)
5. Add `extract_tags` to `ai_service.py`:
   - Write a function `extract_tags` that takes user's text and uses Gemini API (`generate_text(prompt, json_mode=True)`) to extract a small set of "hard tags" (e.g. `["фокус-на-деньгах", "кризис-отношений", "выгорание"]`).
   - The extraction should return a list of strings.
6. Update Database/User schema for `tags`:
   - By default, add an empty `tags` array/list into `database.py:create_user` payload (`"tags": []`).
   - Since users might already exist, make sure that `tags` can be retrieved/updated as a property on the `user` dict.
7. Use `extract_tags` in `modules/tarot.py` and `modules/payments.py`:
   - Create an async task that runs *after* the generation text is sent to the user. It takes the text, extracts tags, and updates the DB via `update_user`.
8. Embed `tags` in `ai_service.py:generate_section`:
   - Add a `tags: list = None` parameter to `generate_section`.
   - If `tags` exist, append a specific instruction to `base_info` or `prompt` (like "Вижу, что прошлый раз был фокус на [tags]. Давай посмотрим, как новая энергия решит твою проблему. Начни текст с отсылки к этим темам.").
9. Pass `tags` to `generate_section` from everywhere:
   - Read `user.get("tags", [])` and pass it to `generate_section` in `modules/tarot.py`, `modules/payments.py`, `modules/services.py`, `main.py` (morning push).
10. Pre-commit checks
11. Submit