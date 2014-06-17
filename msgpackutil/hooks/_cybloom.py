from warnings import warn
from msgpackutil.base import Hook, HOOKS

__author__ = 'basca'

_COUNT = 'c'
_BYTES = 'b'
_SIZE = 's'
_HASHES = 'h'


class BloomFilterHook(Hook):
    def reduce(self, bloom_filter):
        return {
            _COUNT: bloom_filter.count,
            _SIZE: bloom_filter.size,
            _HASHES: bloom_filter.hashes,
            _BYTES: bloom_filter.get_bytes(),
        }


    def create(self, bloom_filter_dict):
        bfilter = BloomFilter(bloom_filter_dict[_SIZE], hashes=bloom_filter_dict[_HASHES],
                              count=bloom_filter_dict[_COUNT])
        bfilter.set_bytes(bloom_filter_dict[_BYTES])
        return bfilter


try:
    from cybloom import BloomFilter

    HOOKS.register(5, BloomFilterHook)
except ImportError:
    warn("could not find cybloom, BloomFilterHook not registered.")