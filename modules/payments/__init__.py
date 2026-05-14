from .handlers import labeler as handlers_labeler, money_transfer_handler, donut_handler
from .callbacks import labeler as callbacks_labeler, message_event_handler
from .logic import process_payment_and_generate, execute_generation

from vkbottle.bot import BotLabeler

labeler = BotLabeler()
labeler.load(handlers_labeler)
labeler.load(callbacks_labeler)

__all__ = ["labeler", "process_payment_and_generate", "execute_generation", "money_transfer_handler", "donut_handler", "message_event_handler"]
