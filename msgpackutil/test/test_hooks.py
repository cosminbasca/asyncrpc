from pandas import DataFrame, Series
from unittest import TestCase
from msgpack import packb, unpackb
import msgpackutil
from pandas.util.testing import assert_frame_equal

__author__ = 'basca'

def assertFrameEqual( df1, df2, **kwds ):
    return assert_frame_equal( df1.sort( axis=1) , df2.sort( axis=1) , check_names = True, **kwds )

class TestHooks(TestCase):
    def test_data_frame(self):
        data = {'one' : Series([1., 2., 3., 10.], index=['a', 'b', 'c']),
            'two' : Series([1., 2., 3., 4.], index=['a', 'b', 'c', 'd'])}
        df = DataFrame(data)
        df_bytes = packb(df)
        self.assertIsNotNone(df_bytes)
        self.assertGreater(len(df_bytes), 0)

        _df = unpackb(df_bytes)
        self.assertIsInstance(_df, DataFrame)
        self.assertEqual(len(df), len(_df))

        assertFrameEqual(df, _df)

    def test_default(self):
        data = {'one' : [1., 2., 3.], 'two' : [1., 2., 3., 4.]}
        _bytes = packb(data)
        self.assertIsNotNone(_bytes)
        self.assertGreater(len(_bytes), 0)

        _data = unpackb(_bytes)
        self.assertIsInstance(_data, dict)
        self.assertEqual(set(data.keys()), set(_data.keys()))
