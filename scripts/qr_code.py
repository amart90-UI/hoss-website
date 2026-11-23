"""Minimal QR code encoder (byte mode, error correction level M, versions 1-10).

Pure Python so the site build needs no QR dependency. Supports URLs of up to
213 bytes. `make_qr("https://example.com")` returns a list of rows of booleans
(True = dark module), without the quiet zone.
"""

# Per version (index = version): error correction codewords per block and block count, level M.
_ECC_PER_BLOCK = [None, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26]
_NUM_BLOCKS = [None, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5]
MAX_VERSION = 10
_FORMAT_BITS_M = 0  # the two-bit indicator for level M


class QRError(Exception):
    """The text does not fit in a supported QR code."""


def _gf_multiply(x, y):
    """Multiply in GF(256) with the QR polynomial 0x11D."""
    result = 0
    for i in range(7, -1, -1):
        result = (result << 1) ^ ((result >> 7) * 0x11D)
        result ^= ((y >> i) & 1) * x
    return result


def _rs_divisor(degree):
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _gf_multiply(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _gf_multiply(root, 2)
    return result


def _rs_remainder(data, divisor):
    result = [0] * len(divisor)
    for byte in data:
        factor = byte ^ result.pop(0)
        result.append(0)
        for i, coefficient in enumerate(divisor):
            result[i] ^= _gf_multiply(coefficient, factor)
    return result


def _raw_data_modules(version):
    result = (16 * version + 128) * version + 64
    if version >= 2:
        count = version // 7 + 2
        result -= (25 * count - 10) * count - 55
        if version >= 7:
            result -= 36
    return result


def _data_codewords(version):
    return _raw_data_modules(version) // 8 - _ECC_PER_BLOCK[version] * _NUM_BLOCKS[version]


def _alignment_positions(version):
    if version == 1:
        return []
    count = version // 7 + 2
    step = (version * 4 + count * 2 + 1) // (count * 2 - 2) * 2
    size = version * 4 + 17
    return sorted([6] + [size - 7 - i * step for i in range(count - 1)])


def _build_codewords(data, version):
    """Add error correction to the data codewords and interleave the blocks."""
    blocks_total = _NUM_BLOCKS[version]
    ecc_length = _ECC_PER_BLOCK[version]
    raw_codewords = _raw_data_modules(version) // 8
    short_blocks = blocks_total - raw_codewords % blocks_total
    short_length = raw_codewords // blocks_total
    divisor = _rs_divisor(ecc_length)
    blocks = []
    start = 0
    for i in range(blocks_total):
        end = start + short_length - ecc_length + (0 if i < short_blocks else 1)
        chunk = data[start:end]
        start = end
        ecc = _rs_remainder(chunk, divisor)
        if i < short_blocks:
            chunk = chunk + [0]  # placeholder so all blocks have equal length
        blocks.append(chunk + ecc)
    result = []
    for i in range(len(blocks[0])):
        for j, block in enumerate(blocks):
            if i != short_length - ecc_length or j >= short_blocks:
                result.append(block[i])
    return result


class _Grid:
    def __init__(self, version):
        self.version = version
        self.size = version * 4 + 17
        self.modules = [[False] * self.size for _ in range(self.size)]
        self.is_function = [[False] * self.size for _ in range(self.size)]
        self._draw_function_patterns()

    def _set(self, x, y, dark):
        self.modules[y][x] = dark
        self.is_function[y][x] = True

    def _draw_function_patterns(self):
        size = self.size
        for i in range(size):
            self._set(6, i, i % 2 == 0)
            self._set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < size and 0 <= y < size:
                        self._set(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        positions = _alignment_positions(self.version)
        last = len(positions) - 1
        for i, cx in enumerate(positions):
            for j, cy in enumerate(positions):
                if (i == 0 and j == 0) or (i == 0 and j == last) or (i == last and j == 0):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self._set(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)
        self._draw_format(0)
        self._draw_version()

    def _draw_format(self, mask):
        size = self.size
        data = _FORMAT_BITS_M << 3 | mask
        remainder = data
        for _ in range(10):
            remainder = (remainder << 1) ^ ((remainder >> 9) * 0x537)
        bits = (data << 10 | remainder) ^ 0x5412

        def bit(i):
            return (bits >> i) & 1 != 0

        for i in range(6):
            self._set(8, i, bit(i))
        self._set(8, 7, bit(6))
        self._set(8, 8, bit(7))
        self._set(7, 8, bit(8))
        for i in range(9, 15):
            self._set(14 - i, 8, bit(i))
        for i in range(8):
            self._set(size - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self._set(8, size - 15 + i, bit(i))
        self._set(8, size - 8, True)

    def _draw_version(self):
        if self.version < 7:
            return
        remainder = self.version
        for _ in range(12):
            remainder = (remainder << 1) ^ ((remainder >> 11) * 0x1F25)
        bits = self.version << 12 | remainder
        for i in range(18):
            dark = (bits >> i) & 1 != 0
            a = self.size - 11 + i % 3
            b = i // 3
            self._set(a, b, dark)
            self._set(b, a, dark)

    def draw_codewords(self, codewords):
        size = self.size
        i = 0
        total_bits = len(codewords) * 8
        for right in range(size - 1, 0, -2):
            if right == 6:
                right = 5
            for vertical in range(size):
                for j in range(2):
                    x = right - j
                    upward = ((right + 1) & 2) == 0
                    y = size - 1 - vertical if upward else vertical
                    if not self.is_function[y][x] and i < total_bits:
                        self.modules[y][x] = (codewords[i >> 3] >> (7 - (i & 7))) & 1 != 0
                        i += 1

    def apply_mask(self, mask):
        conditions = (
            lambda x, y: (x + y) % 2 == 0,
            lambda x, y: y % 2 == 0,
            lambda x, y: x % 3 == 0,
            lambda x, y: (x + y) % 3 == 0,
            lambda x, y: (x // 3 + y // 2) % 2 == 0,
            lambda x, y: x * y % 2 + x * y % 3 == 0,
            lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
            lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
        )
        invert = conditions[mask]
        for y in range(self.size):
            for x in range(self.size):
                if not self.is_function[y][x] and invert(x, y):
                    self.modules[y][x] = not self.modules[y][x]

    def penalty(self):
        size = self.size
        modules = self.modules
        score = 0
        lines = [row for row in modules] + [[modules[y][x] for y in range(size)] for x in range(size)]
        for line in lines:
            run = 1
            for i in range(1, size):
                if line[i] == line[i - 1]:
                    run += 1
                    if run == 5:
                        score += 3
                    elif run > 5:
                        score += 1
                else:
                    run = 1
            text = "".join("1" if value else "0" for value in line)
            score += 40 * (text.count("00001011101") + text.count("10111010000"))
        for y in range(size - 1):
            for x in range(size - 1):
                if modules[y][x] == modules[y][x + 1] == modules[y + 1][x] == modules[y + 1][x + 1]:
                    score += 3
        dark = sum(row.count(True) for row in modules)
        total = size * size
        score += ((abs(dark * 20 - total * 10) + total - 1) // total - 1) * 10
        return score


def make_qr(text):
    """Return the QR code for `text` as rows of booleans (True = dark)."""
    payload = text.encode("utf-8")
    for version in range(1, MAX_VERSION + 1):
        capacity_bits = _data_codewords(version) * 8
        count_bits = 8 if version <= 9 else 16
        if 4 + count_bits + len(payload) * 8 <= capacity_bits:
            break
    else:
        raise QRError(f"text is too long for a version {MAX_VERSION} QR code ({len(payload)} bytes)")

    bits = [0, 1, 0, 0]
    bits += [(len(payload) >> i) & 1 for i in range(count_bits - 1, -1, -1)]
    for byte in payload:
        bits += [(byte >> i) & 1 for i in range(7, -1, -1)]
    bits += [0] * min(4, capacity_bits - len(bits))
    bits += [0] * (-len(bits) % 8)
    data = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(data) < capacity_bits // 8:
        data.append(pad)
        pad ^= 0xEC ^ 0x11

    codewords = _build_codewords(data, version)
    best = None
    for mask in range(8):
        grid = _Grid(version)
        grid.draw_codewords(codewords)
        grid.apply_mask(mask)
        grid._draw_format(mask)
        score = grid.penalty()
        if best is None or score < best[0]:
            best = (score, grid)
    return best[1].modules
