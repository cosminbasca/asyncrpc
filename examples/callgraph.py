from asyncrpc import AsyncManager
from pycallgraph import PyCallGraph
from pycallgraph.output import GraphvizOutput
import string
import random
from pandas import DataFrame

__author__ = 'basca'


def random_string(size):
    return ''.join(random.choice(string.ascii_uppercase) for i in range(size))


class DataStore(object):
    def __init__(self, rows, columns):
        self._rows = rows
        self._columns = columns
        self._data_columns = ['COLUMN_{0}'.format(i) for i in range(columns)]
        self._data = DataFrame(
            data=[[random_string(30) for j in range(self._columns)] for i in range(self._rows)],
            columns=self._data_columns
        )

    def num_rows(self):
        return self._rows

    def num_columns(self):
        return self._columns

    def get_slice(self, row_idx, col_idx):
        return self._data.iloc[row_idx, col_idx]


class StoreManager(AsyncManager):
    pass


StoreManager.register('DataStore', DataStore)


def main():
    manager = StoreManager()
    manager.start()

    rows = 30
    cols = 4
    print 'creating a store with {0} rows nad {1} columns'.format(rows, cols)
    store = manager.DataStore(rows, cols)
    print 'store reported rows      = ', store.num_rows()
    print 'store reported columns   = ', store.num_columns()
    for i in xrange(10):
        slice = store.get_slice(range(0, i + 1), range(1, 3))
        print 'got slice'
        print slice


# call
# python -m cProfile -o output.pstats ./examples/callgraph.py
# gprof2dot.py -f pstats output.pstats | dot -Tpng -o output.png
if __name__ == '__main__':
    graphviz = GraphvizOutput()
    graphviz.output_file = 'callgraph_example_datastore.png'

    with PyCallGraph(output=graphviz):
        main()


