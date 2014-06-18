from pandas import DataFrame, Series
from msgpackutil.base import Hook, HOOKS

__author__ = 'basca'

_DATA = 'd'
_COLS = 'c'
_INDEX = 'i'


class DataFrameHook(Hook):
    @property
    def type(self):
        return DataFrame

    def reduce(self, data_frame):
        _index = data_frame.index
        data_frame_dict = {
            _DATA: data_frame.values.tolist(),
            _COLS: data_frame.columns.tolist()}
        if _index.dtype != int:
            data_frame_dict[_INDEX] = data_frame.index.tolist()
        return data_frame_dict

    def create(self, data_frame_dict):
        data = list(data_frame_dict[_DATA])
        columns = data_frame_dict[_COLS]
        if data:
            if _INDEX in data_frame_dict:
                return DataFrame(data=data, columns=columns, index=data_frame_dict[_INDEX])
            else:
                return DataFrame(data=data, columns=columns)
        else:
            return DataFrame(columns=columns)


class SeriesHook(Hook):
    @property
    def type(self):
        return Series

    def reduce(self, series):
        _index = series.index
        series_dict = {
            _DATA: series.values.tolist(),
        }
        if _index.dtype != int:
            series_dict[_INDEX] = [i for i in _index]
        return series_dict

    def create(self, series_dict):
        data = list(series_dict[_DATA])
        if data:
            if _INDEX in series_dict:
                return Series(data=data, index=series_dict[_INDEX])
            else:
                return Series(data=data)
        else:
            return Series()


HOOKS.register(1, DataFrameHook)
HOOKS.register(2, SeriesHook)