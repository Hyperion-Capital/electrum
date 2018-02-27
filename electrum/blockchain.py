# Electrum - lightweight Bitcoin client
# Copyright (C) 2012 thomasv@ecdsa.org
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import os
import threading

from . import util
from .bitcoin import Hash, hash_encode, int_to_hex, rev_hex
from .crypto import PoWHash
from . import constants
from .util import bfh, bh2u

MAX_TARGET = 0x00000FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
SEVEN_DAYS = 7 * 24 * 60 * 60
HEIGHT_FORK_ONE = 33000



class MissingHeader(Exception):
    pass

class InvalidHeader(Exception):
    pass

def serialize_header(res):
    s = int_to_hex(res.get('version'), 4) \
        + rev_hex(res.get('prev_block_hash')) \
        + rev_hex(res.get('merkle_root')) \
        + int_to_hex(int(res.get('timestamp')), 4) \
        + int_to_hex(int(res.get('bits')), 4) \
        + int_to_hex(int(res.get('nonce')), 4)
    return s

def deserialize_header(s, height):
    if not s:
        raise InvalidHeader('Invalid header: {}'.format(s))
    if len(s) != 80:
        raise InvalidHeader('Invalid header length: {}'.format(len(s)))
    hex_to_int = lambda s: int('0x' + bh2u(s[::-1]), 16)
    h = {}
    h['version'] = hex_to_int(s[0:4])
    h['prev_block_hash'] = hash_encode(s[4:36])
    h['merkle_root'] = hash_encode(s[36:68])
    h['timestamp'] = hex_to_int(s[68:72])
    h['bits'] = hex_to_int(s[72:76])
    h['nonce'] = hex_to_int(s[76:80])
    h['block_height'] = height
    return h

def pow_hash_header(header):
    if header is None:
        return '0' * 64
    if header.get('prev_block_hash') is None:
        header['prev_block_hash'] = '00'*32
    return hash_encode(PoWHash(bfh(serialize_header(header))))

def hash_header(header):
    if header is None:
        return '0' * 64
    if header.get('prev_block_hash') is None:
        header['prev_block_hash'] = '00'*32
    return hash_encode(Hash(bfh(serialize_header(header))))


blockchains = {}

def read_blockchains(config):
    blockchains[0] = Blockchain(config, 0, None)
    fdir = os.path.join(util.get_headers_dir(config), 'forks')
    util.make_dir(fdir)
    l = filter(lambda x: x.startswith('fork_'), os.listdir(fdir))
    l = sorted(l, key = lambda x: int(x.split('_')[1]))
    for filename in l:
        forkpoint = int(filename.split('_')[2])
        parent_id = int(filename.split('_')[1])
        b = Blockchain(config, forkpoint, parent_id)
        h = b.read_header(b.forkpoint)
        if b.parent().can_connect(h, check_height=False):
            blockchains[b.forkpoint] = b
        else:
            util.print_error("cannot connect", filename)
    return blockchains

def check_header(header):
    if type(header) is not dict:
        return False
    for b in blockchains.values():
        if b.check_header(header):
            return b
    return False

def can_connect(header):
    for b in blockchains.values():
        if b.can_connect(header):
            return b
    return False


class Blockchain(util.PrintError):
    """
    Manages blockchain headers and their verification
    """

    def __init__(self, config, forkpoint, parent_id):
        self.config = config
        self.catch_up = None  # interface catching up
        self.forkpoint = forkpoint
        self.checkpoints = constants.net.CHECKPOINTS
        self.parent_id = parent_id
        assert parent_id != forkpoint
        self.lock = threading.RLock()
        with self.lock:
            self.update_size()

    def with_lock(func):
        def func_wrapper(self, *args, **kwargs):
            with self.lock:
                return func(self, *args, **kwargs)
        return func_wrapper

    def parent(self):
        return blockchains[self.parent_id]

    def get_max_child(self):
        children = list(filter(lambda y: y.parent_id==self.forkpoint, blockchains.values()))
        return max([x.forkpoint for x in children]) if children else None

    def get_forkpoint(self):
        mc = self.get_max_child()
        return mc if mc is not None else self.forkpoint

    def get_branch_size(self):
        return self.height() - self.get_forkpoint() + 1

    def get_name(self):
        return self.get_hash(self.get_forkpoint()).lstrip('00')[0:10]

    def check_header(self, header):
        header_hash = hash_header(header)
        height = header.get('block_height')
        return header_hash == self.get_hash(height)

    def fork(parent, header):
        forkpoint = header.get('block_height')
        self = Blockchain(parent.config, forkpoint, parent.forkpoint)
        open(self.path(), 'w+').close()
        self.save_header(header)
        return self

    def height(self):
        return self.forkpoint + self.size() - 1

    def size(self):
        with self.lock:
            return self._size

    def update_size(self):
        p = self.path()
        self._size = os.path.getsize(p)//80 if os.path.exists(p) else 0

    def verify_header(self, header, prev_hash, target):
        _hash = pow_hash_header(header)
        if prev_hash != header.get('prev_block_hash'):
            raise Exception("prev hash mismatch: %s vs %s" % (prev_hash, header.get('prev_block_hash')))
        if constants.net.TESTNET:
            return
        if header.get('block_height') >= len(self.checkpoints) * 2016:
            bits = self.target_to_bits(target)
            if bits != header.get('bits'):
                raise Exception("bits mismatch: %s vs %s" % (bits, header.get('bits')))
            if int('0x' + _hash, 16) > target:
                raise Exception("insufficient proof of work: %s vs target %s" % (int('0x' + _hash, 16), target))

    def verify_chunk(self, index, data):
        num = len(data) // 80
        prev_hash = self.get_hash(index * 2016 - 1)
        headers = []
        for i in range(num):
            raw_header = data[i*80:(i+1) * 80]
            headers.append(deserialize_header(raw_header, index*2016 + i))
        for i, header in enumerate(headers):
            target = self.get_target(index*2016 + i, headers)
            self.verify_header(header, prev_hash, target)
            prev_hash = hash_header(header)

    def path(self):
        d = util.get_headers_dir(self.config)
        filename = 'blockchain_headers' if self.parent_id is None else os.path.join('forks', 'fork_%d_%d'%(self.parent_id, self.forkpoint))
        return os.path.join(d, filename)

    @with_lock
    def save_chunk(self, index, chunk):
        chunk_within_checkpoint_region = index < len(self.checkpoints)
        # chunks in checkpoint region are the responsibility of the 'main chain'
        if chunk_within_checkpoint_region and self.parent_id is not None:
            main_chain = blockchains[0]
            main_chain.save_chunk(index, chunk)
            return

        delta_height = (index * 2016 - self.forkpoint)
        delta_bytes = delta_height * 80
        # if this chunk contains our forkpoint, only save the part after forkpoint
        # (the part before is the responsibility of the parent)
        if delta_bytes < 0:
            chunk = chunk[-delta_bytes:]
            delta_bytes = 0
        truncate = not chunk_within_checkpoint_region
        self.write(chunk, delta_bytes, truncate)
        self.swap_with_parent()

    @with_lock
    def swap_with_parent(self):
        if self.parent_id is None:
            return
        parent_branch_size = self.parent().height() - self.forkpoint + 1
        if parent_branch_size >= self.size():
            return
        self.print_error("swap", self.forkpoint, self.parent_id)
        parent_id = self.parent_id
        forkpoint = self.forkpoint
        parent = self.parent()
        self.assert_headers_file_available(self.path())
        with open(self.path(), 'rb') as f:
            my_data = f.read()
        self.assert_headers_file_available(parent.path())
        with open(parent.path(), 'rb') as f:
            f.seek((forkpoint - parent.forkpoint)*80)
            parent_data = f.read(parent_branch_size*80)
        self.write(parent_data, 0)
        parent.write(my_data, (forkpoint - parent.forkpoint)*80)
        # store file path
        for b in blockchains.values():
            b.old_path = b.path()
        # swap parameters
        self.parent_id = parent.parent_id; parent.parent_id = parent_id
        self.forkpoint = parent.forkpoint; parent.forkpoint = forkpoint
        self._size = parent._size; parent._size = parent_branch_size
        # move files
        for b in blockchains.values():
            if b in [self, parent]: continue
            if b.old_path != b.path():
                self.print_error("renaming", b.old_path, b.path())
                os.rename(b.old_path, b.path())
        # update pointers
        blockchains[self.forkpoint] = self
        blockchains[parent.forkpoint] = parent

    def assert_headers_file_available(self, path):
        if os.path.exists(path):
            return
        elif not os.path.exists(util.get_headers_dir(self.config)):
            raise FileNotFoundError('Electrum headers_dir does not exist. Was it deleted while running?')
        else:
            raise FileNotFoundError('Cannot find headers file but headers_dir is there. Should be at {}'.format(path))

    def write(self, data, offset, truncate=True):
        filename = self.path()
        with self.lock:
            self.assert_headers_file_available(filename)
            with open(filename, 'rb+') as f:
                if truncate and offset != self._size*80:
                    f.seek(offset)
                    f.truncate()
                f.seek(offset)
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            self.update_size()

    @with_lock
    def save_header(self, header):
        delta = header.get('block_height') - self.forkpoint
        data = bfh(serialize_header(header))
        # headers are only _appended_ to the end:
        assert delta == self.size()
        assert len(data) == 80
        self.write(data, delta*80)
        self.swap_with_parent()

    def read_header(self, height):
        assert self.parent_id != self.forkpoint
        if height < 0:
            return
        if height < self.forkpoint:
            return self.parent().read_header(height)
        if height > self.height():
            return
        delta = height - self.forkpoint
        name = self.path()
        self.assert_headers_file_available(name)
        with open(name, 'rb') as f:
            f.seek(delta * 80)
            h = f.read(80)
            if len(h) < 80:
                raise Exception('Expected to read a full header. This was only {} bytes'.format(len(h)))
        if h == bytes([0])*80:
            return None
        return deserialize_header(h, height)

    def get_hash(self, height):
        if height == -1:
            return '0000000000000000000000000000000000000000000000000000000000000000'
        elif height == 0:
            return constants.net.GENESIS
        elif height < len(self.checkpoints) * 2016:
            assert (height+1) % 2016 == 0, height
            index = height // 2016
            return self.checkpoints[index]
        else:
            return hash_header(self.read_header(height))

    def get_target(self, height, headers):
        if constants.net.TESTNET:
            return 0
        if height == 0:
            return MAX_TARGET
        if height < len(self.checkpoints) * 2016:
            # return pessimistic value to detect if check is unintentionally performed
            return 0
        if height == len(self.checkpoints) * 2016:
            # this value needs to be updated every time
            # `checkpoints.json` is updated
            return 143256919707644724074290378570122304852251874692742198474282369024
        elif height >= HEIGHT_FORK_ONE:
            return self.__fork_one_target(height, headers)
        else:
            return self.__vanilla_target(height, headers)

    def __fork_one_target(self, height, headers):
        interval = 504
        last_height = height - 1
        last = self.get_header(last_height, height, headers)
        if not last:
            raise MissingHeader()
        target = self.bits_to_target(last.get('bits'))
        if height % interval != 0 and height != HEIGHT_FORK_ONE:
            return target
        first = self.get_header(last_height - interval, height, headers)
        if not first:
            raise MissingHeader()
        nActualTimespan = last.get('timestamp') - first.get('timestamp')
        return Blockchain.__get_target(target, nActualTimespan, SEVEN_DAYS // 8, 70, 99)

    def __vanilla_target(self, height, headers):
        interval = 2016
        last_height = height - 1
        last = self.get_header(last_height, height, headers)
        if not last:
            raise MissingHeader()
        bits = last.get('bits')
        target = self.bits_to_target(bits)
        if height % interval != 0:
            return target
        first = self.get_header(max(0, last_height - interval), height, headers)
        if not first:
            raise MissingHeader()
        nActualTimespan = last.get('timestamp') - first.get('timestamp')
        return Blockchain.__get_target(target, nActualTimespan, SEVEN_DAYS // 2, 1, 4)

    @staticmethod
    def __get_target(target, nActualTimespan, nTargetTimespan, numerator, denominator):
        nActualTimespan = max(nActualTimespan, int(nTargetTimespan * numerator / denominator))
        nActualTimespan = min(nActualTimespan, int(nTargetTimespan * denominator / numerator))
        new_target = min(MAX_TARGET, int(target * nActualTimespan / nTargetTimespan))
        return new_target

    def get_header(self, height, ref_height, headers):
        delta = ref_height % 2016
        if height < ref_height - delta or headers is None:
            return self.read_header(height)
        return headers[delta - (ref_height - height)]

    def bits_to_target(self, bits):
        bitsN = (bits >> 24) & 0xff
        if not (bitsN >= 0x03 and bitsN <= 0x1e):
            raise Exception("First part of bits should be in [0x03, 0x1e]")
        bitsBase = bits & 0xffffff
        if not (bitsBase >= 0x8000 and bitsBase <= 0x7fffff):
            raise Exception("Second part of bits should be in [0x8000, 0x7fffff]")
        return bitsBase << (8 * (bitsN-3))

    def target_to_bits(self, target):
        c = ("%064x" % target)[2:]
        while c[:2] == '00' and len(c) > 6:
            c = c[2:]
        bitsN, bitsBase = len(c) // 2, int('0x' + c[:6], 16)
        if bitsBase >= 0x800000:
            bitsN += 1
            bitsBase >>= 8
        return bitsN << 24 | bitsBase

    def can_connect(self, header, check_height=True):
        if header is None:
            return False
        height = header['block_height']
        if check_height and self.height() != height - 1:
            #self.print_error("cannot connect at height", height)
            return False
        if height == 0:
            return hash_header(header) == constants.net.GENESIS
        try:
            prev_hash = self.get_hash(height - 1)
        except:
            return False
        if prev_hash != header.get('prev_block_hash'):
            return False
        try:
            target = self.get_target(height, None)
        except MissingHeader:
            return False
        try:
            self.verify_header(header, prev_hash, target)
        except BaseException as e:
            return False
        return True

    def connect_chunk(self, idx, hexdata):
        try:
            data = bfh(hexdata)
            self.verify_chunk(idx, data)
            #self.print_error("validated chunk %d" % idx)
            self.save_chunk(idx, data)
            return True
        except BaseException as e:
            self.print_error('verify_chunk %d failed'%idx, str(e))
            return False

    def get_checkpoints(self):
        # for each chunk, store the hash of the last block and the target after the chunk
        n = self.height() // 2016
        return [self.get_hash((i+1) * 2016 -1) for i in range(n)]
