from aiogram.fsm.state import State, StatesGroup


class ChannelAddStates(StatesGroup):
    waiting_username = State()


class SearchStates(StatesGroup):
    waiting_query = State()
