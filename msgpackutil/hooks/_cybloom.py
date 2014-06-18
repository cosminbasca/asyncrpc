from warnings import warn
from msgpackutil.base import Hook, HOOKS

__author__ = 'basca'

_COUNT = 'c'
_BYTES = 'b'
_SIZE = 's'
_HASHES = 'h'
_CAP = 'n'


class BloomFilterHook(Hook):
    @property
    def type(self):
        return BloomFilter

    def reduce(self, bloom_filter):
        bloom_filter_dict = {
            _COUNT: bloom_filter.count,
            _SIZE: bloom_filter.size,
            _HASHES: bloom_filter.hashes,
            _BYTES: bloom_filter.get_bytes(),
            _CAP: bloom_filter.capacity}
        return bloom_filter_dict

    def create(self, bloom_filter_dict):
        bfilter = BloomFilter(bloom_filter_dict[_SIZE], bloom_filter_dict[_CAP],
                              hashes=bloom_filter_dict[_HASHES], count=bloom_filter_dict[_COUNT])
        bfilter.set_bytes(bloom_filter_dict[_BYTES])
        return bfilter


try:
    from cybloom import BloomFilter

    HOOKS.register(5, BloomFilterHook)
except ImportError:
    warn("could not find cybloom, BloomFilterHook not registered.")