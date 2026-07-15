from aiogram.fsm.state import State, StatesGroup


class SearchStates(StatesGroup):
    waiting_query = State()


class HistoryStates(StatesGroup):
    waiting_query = State()


class ChannelBulkStates(StatesGroup):
    waiting_list = State()


class IgnoreTopicsStates(StatesGroup):
    waiting_topics = State()


class AdminAuthStates(StatesGroup):
    create_password = State()
    confirm_password = State()
    enter_password = State()
    menu = State()
    find_user = State()
    appoint_admin = State()


class TimezoneStates(StatesGroup):
    waiting_tz = State()
