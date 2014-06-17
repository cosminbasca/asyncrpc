from pandas import DataFrame, Series
from msgpackutil.base import Hook, HOOKS

__author__ = 'basca'

_DATA = 'd'
_COLS = 'c'
_INDEX = 'i'


class DataFrameHook(Hook):
    def reduce(self, data_frame):
        # _itertuples = data_frame.itertuples
        # _columns = data_frame.columns
        # return {
        # _DATA: [t for t in _itertuples(index=False)],
        # _COLS: [c for c in _columns]
        # }
        # _columns = data_frame.columns
        return {
            _DATA: data_frame.values.tolist(),
            _COLS: data_frame.columns.tolist()
            # _INDEX: data_frame.index.tolist()
        }


    def create(self, data_frame_dict):
        # data = list(data_frame_dict[_DATA])
        # return DataFrame(
        # data=data,
        # columns=data_frame_dict[_COLS]
        # ) if data else DataFrame(columns=data_frame_dict[_COLS])
        data = list(data_frame_dict[_DATA])
        return DataFrame(
            data=data,
            columns=data_frame_dict[_COLS]
            # index=data_frame_dict[_INDEX]
        ) if data else DataFrame(columns=data_frame_dict[_COLS])


class SeriesHook(Hook):
    def reduce(self, series):
        return {
            _DATA: series.values.tolist(),
            _INDEX: series.index.tolist()
        }


    def create(self, series_dict):
        data = list(series_dict[_DATA])
        return Series(
            data=series_dict[_DATA],
            index=series_dict[_INDEX]
        ) if data else Series()


HOOKS.register(1, DataFrameHook)
HOOKS.register(2, SeriesHook)