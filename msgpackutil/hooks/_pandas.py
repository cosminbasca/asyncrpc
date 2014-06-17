from pandas import DataFrame
from msgpackutil.base import Hook, HOOKS

__author__ = 'basca'

_DATA = 'd'
_COLS = 'c'


class DataFrameHook(Hook):
    def reduce(self, data_frame):
        _itertuples = data_frame.itertuples
        _columns = data_frame.columns
        return {
            _DATA: [t for t in _itertuples(index=False)],
            _COLS: [c for c in _columns]
        }


    def create(self, data_frame_dict):
        data = list(data_frame_dict[_DATA])
        return DataFrame(
            data=data,
            columns=data_frame_dict[_COLS]
        ) if data else DataFrame(columns=data_frame_dict[_COLS])


HOOKS.register(1, DataFrameHook)