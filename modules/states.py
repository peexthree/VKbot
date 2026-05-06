from vkbottle import BaseStateGroup

class MyStates(BaseStateGroup):
    WAITING_FOR_ONBOARDING_DATA = "waiting_for_onboarding_data"
    WAITING_SYNASTRY_DATE = "waiting_synastry_date"
    WAITING_ORACLE_QUESTION = "waiting_oracle_question"
    ORACLE_DRAW = "oracle_draw"
    GLOBAL_CUT = "global_cut"
    WAITING_RESET_CONFIRM = "waiting_reset_confirm"
