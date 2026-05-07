1. **Remove long-running loop that sends static text.**
    Currently in `modules/tarot.py` (and potentially other places), `send_typing_indicator` runs an infinite loop waiting `asyncio.sleep(5)` and sending "Ожидайте, идет генерация ответа...".
2. **Implement `start_dynamic_typing` Utility.**
    In `modules/utils.py`, add a utility function `start_dynamic_typing` that accepts `bot_api`, `peer_id`, and `message_id`. It will loop, wait 10s, pick a random phrase from `THEATRICAL_PHRASES`, edit the message, and set "typing" activity.
3. **Refactor generation wrappers.**
    Update `card_of_day_logic` in `modules/tarot.py` to:
    - Send an initial theatrical phrase immediately, capturing the `message_id`.
    - Start `start_dynamic_typing` task.
    - Call generation API.
    - Cancel the task.
    - Delete the theatrical message before sending the result (or replace it).
4. Apply the same logic in `process_oracle_final` in `modules/tarot.py` and `execute_generation` in `modules/payments.py`.
