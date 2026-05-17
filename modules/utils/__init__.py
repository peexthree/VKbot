def __getattr__(name):
    if name in ["THEATRICAL_PHRASES", "SKIN_ASSETS", "ADMIN_ID", "pdf_semaphore"]:
        from .consts import THEATRICAL_PHRASES, SKIN_ASSETS, ADMIN_ID, pdf_semaphore
        globals()["THEATRICAL_PHRASES"] = THEATRICAL_PHRASES
        globals()["SKIN_ASSETS"] = SKIN_ASSETS
        globals()["ADMIN_ID"] = ADMIN_ID
        globals()["pdf_semaphore"] = pdf_semaphore
        return globals()[name]

    if name in [
        "ghost_edit", "stop_dynamic_typing", "start_dynamic_typing",
        "delete_bot_message", "get_last_bot_msg", "set_last_bot_msg", "send_temp_message"
    ]:
        from .ui import (
            ghost_edit, stop_dynamic_typing, start_dynamic_typing,
            delete_bot_message, get_last_bot_msg, set_last_bot_msg, send_temp_message
        )
        globals()["ghost_edit"] = ghost_edit
        globals()["stop_dynamic_typing"] = stop_dynamic_typing
        globals()["start_dynamic_typing"] = start_dynamic_typing
        globals()["delete_bot_message"] = delete_bot_message
        globals()["get_last_bot_msg"] = get_last_bot_msg
        globals()["set_last_bot_msg"] = set_last_bot_msg
        globals()["send_temp_message"] = send_temp_message
        return globals()[name]

    if name in ["get_cached_photo", "flush_anchors", "upload_local_photo", "warmup_task", "clear_photo_cache"]:
        from .photos import (
            get_cached_photo, flush_anchors, upload_local_photo, warmup_task, clear_photo_cache
        )
        globals()["get_cached_photo"] = get_cached_photo
        globals()["flush_anchors"] = flush_anchors
        globals()["upload_local_photo"] = upload_local_photo
        globals()["warmup_task"] = warmup_task
        globals()["clear_photo_cache"] = clear_photo_cache
        return globals()[name]

    if name == "generate_premium_pdf":
        from .pdf import generate_premium_pdf
        globals()["generate_premium_pdf"] = generate_premium_pdf
        return generate_premium_pdf

    if name in ["get_main_keyboard", "get_dynamic_keyboard", "get_sections_keyboard", "get_storefront_keyboard"]:
        from .keyboards import (
            get_main_keyboard, get_dynamic_keyboard, get_sections_keyboard, get_storefront_keyboard
        )
        globals()["get_main_keyboard"] = get_main_keyboard
        globals()["get_dynamic_keyboard"] = get_dynamic_keyboard
        globals()["get_sections_keyboard"] = get_sections_keyboard
        globals()["get_storefront_keyboard"] = get_storefront_keyboard
        return globals()[name]

    if name in ["get_fsm_step", "check_and_give_daily_bonus"]:
        from .logic import get_fsm_step, check_and_give_daily_bonus
        globals()["get_fsm_step"] = get_fsm_step
        globals()["check_and_give_daily_bonus"] = check_and_give_daily_bonus
        return globals()[name]

    if name in ["acquire_lock", "release_lock"]:
        from cache import acquire_lock, release_lock
        globals()["acquire_lock"] = acquire_lock
        globals()["release_lock"] = release_lock
        return globals()[name]

    raise AttributeError(f"module {__name__} has no attribute {name}")

__all__ = [
    "THEATRICAL_PHRASES", "SKIN_ASSETS", "ADMIN_ID", "pdf_semaphore",
    "ghost_edit", "stop_dynamic_typing", "start_dynamic_typing",
    "delete_bot_message", "get_last_bot_msg", "set_last_bot_msg", "send_temp_message",
    "get_cached_photo", "flush_anchors", "upload_local_photo", "warmup_task", "clear_photo_cache",
    "generate_premium_pdf",
    "get_main_keyboard", "get_dynamic_keyboard", "get_sections_keyboard", "get_storefront_keyboard",
    "get_fsm_step", "check_and_give_daily_bonus", "acquire_lock", "release_lock"
]
