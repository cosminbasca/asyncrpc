from time import time
import numpy as np
from pandas import DataFrame

__author__ = 'basca'

def main():
    data = [range(100) for i in xrange(100000) ]
    df = DataFrame(data)

    t0 = time()
    v = df.values.tolist()
    print '[numpy tolist        ] took {0} seconds'.format(time()-t0)

    _itertuples = df.itertuples
    t0 = time()
    v = [r for r in _itertuples(index=False)]
    print '[list comprehension  ] took {0} seconds'.format(time()-t0)


if __name__ == '__main__':
    main()


