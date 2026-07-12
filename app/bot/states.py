from aiogram.fsm.state import State, StatesGroup


class SearchStates(StatesGroup):
    waiting_query = State()


class ChannelBulkStates(StatesGroup):
    waiting_list = State()


class IgnoreTopicsStates(StatesGroup):
    waiting_topics = State()
