1. **Add `extract_tags` to `ai_service.py`**:
   - Write a function `extract_tags` that takes user's text (and potentially a previous response or section type) and uses Gemini API (`generate_text(prompt, json_mode=True)`) to extract a small set of "hard tags" (e.g. `["фокус-на-деньгах", "кризис-отношений", "выгорание"]`).
   - The extraction should return a list of strings.
2. **Update Database/User schema for `tags`**:
   - By default, add an empty `tags` array/list into `database.py:create_user` payload (`"tags": []`).
   - Since users might already exist, make sure that `tags` can be retrieved/updated as a property on the `user` dict.
3. **Use `extract_tags` in `modules/tarot.py` and `modules/payments.py`**:
   - When a user gets a generation (e.g. `card_of_day`, `base`, etc.), asynchronously extract tags based on their request/results.
   - Wait, actually, the easiest way is to extract tags directly from the AI response, but to save tokens it might be better to just do it asynchronously after a generation, or add a prompt instruction to the main generation?
   - Wait, the issue says: "После каждого разбора бот присваивает клиенту жесткие теги в базу данных... При следующем визите клиента эти теги незаметно вшиваются в промпт для ИИ".
   - Let's create an async task that runs *after* the generation text is sent to the user. It takes the text, extracts tags, and updates the DB via `update_user`.
4. **Embed `tags` in `ai_service.py:generate_section`**:
   - Add a `tags: list = None` parameter to `generate_section`.
   - If `tags` exist, append a specific instruction to `base_info` or `prompt` (like "Вижу, что прошлый раз был фокус на [tags]. Давай посмотрим, как новая энергия решит твою проблему. Начни текст с отсылки к этим темам.").
5. **Pass `tags` to `generate_section` from everywhere**:
   - Read `user.get("tags", [])` and pass it to `generate_section` in `modules/tarot.py`, `modules/payments.py`, `modules/services.py`, `main.py` (morning push).
6. **Pre-commit checks**
7. **Submit**
