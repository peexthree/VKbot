1. **Fix Flood control error (VKAPIError_9)**
   - In `modules/utils/ui.py`, we will add delay mechanism and flood-control (code 9) recovery to `ghost_edit` and `_typing_loop` (inside `start_dynamic_typing`). If `messages.edit` fails with flood control error, it will wait 1-2 seconds and optionally fallback to `messages.send`.
   - In `modules/payments/callbacks.py`, within `_message_event_handler_wrapped`, we will wrap the direct `bot.api.messages.edit` calls in a robust `try-except` block, first doing `await asyncio.sleep(0.3)` to prevent rapid API calls. If `VKAPIError(9)` happens, fallback to `bot.api.messages.send` and update `last_bot_msg`. Since there are multiple calls to `bot.api.messages.edit` directly, we might create a safe helper function for edits in `callbacks.py` or use `ghost_edit` where appropriate. We'll implement a `safe_edit` helper in `ui.py` or locally and use it to replace direct `edit` calls in `_message_event_handler_wrapped`.

2. **Fix Destiny Card NoneType Error & Add Missing AI Logic**
   - Edit `ai/sections.py`: In `generate_section`, add `elif section == "destiny_card":` and construct a prompt using the same style logic as other sections, incorporating `card_data` for the generated destiny card.
   - Edit `modules/tarot/destiny.py`: In `generate_destiny_card_logic`, add `if not birth_date:` and other None-checks. If `res_text` is empty/None, gracefully revert the user's energy and send an error. Add a check `if res_text is None or not res_text:` before appending.

3. **Update Keyboards according to specification**
   - Edit `modules/keyboards.py`. Update `main_menu_kb`, `services_menu_kb`, `profile_menu_kb`, `settings_menu_kb`, and `after_pdf_kb`. Ensure `services_menu_kb` has exactly "🔮 Все услуги" (without caps) and other specified changes, adhering strictly to limits and structure.

4. **Pre-commit verification**
   - Run tests, check for syntax errors, and confirm no syntax issues in modified files. Ensure pre commit steps to make sure proper testing, verifications, reviews and reflections are done.
