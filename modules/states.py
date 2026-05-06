from vkbottle import BaseStateGroup

class MyStates(BaseStateGroup):
    WAITING_FOR_DATE = "waiting_for_date"
    WAITING_FOR_TIME = "waiting_for_time"
    WAITING_FOR_CITY = "waiting_for_city"
    WAITING_CONFIRM_DATA = "waiting_confirm_data"
    WAITING_SYNASTRY_DATE = "waiting_synastry_date"
    WAITING_ORACLE_QUESTION = "waiting_oracle_question"
    ORACLE_DRAW = "oracle_draw"
    GLOBAL_CUT = "global_cut"
    WAITING_RESET_CONFIRM = "waiting_reset_confirm"
