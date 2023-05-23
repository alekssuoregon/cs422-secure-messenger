from isaac import Isaac
from PIL import Image
import math

class StegoTranscoder:
    def __init__(self, chan_density: int = 2, rearrange_key: bytes = None):
        self._header_size = 16
        self._chan_density = chan_density
        self._key = rearrange_key

    # Message should be a 'bytes' object
    def encode(self, message: bytes, in_img_path: str, out_img_path: str) -> bool:
        # Load image, calculate image size
        img = Image.open(in_img_path)
        pixels = img.load()
        width, height = img.size
        channel_n = len(pixels[0,0])

        # Check if image sufficient size for message
        encodable_bits = width * height * channel_n * self._chan_density 
        msg_bits = self._bytes_to_bitstring(message)
        header_bits = self._int_to_bitstring(int(len(msg_bits) / 8), self._header_size)

        if len(msg_bits) + len(header_bits) > encodable_bits:
            return False
        
        # Encode header in image
        i = 0
        cur_bit_n = 0
        finished_encoding = False
        while i < height and not finished_encoding:
            j = 0
            while j < width and not finished_encoding:
                channels = list(pixels[i, j])
                k = 0
                while k < channel_n:
                    l = 0
                    channels[k] &= (0b11111111 << self._chan_density)
                    while l < self._chan_density and cur_bit_n < self._header_size:
                        channels[k] += (header_bits[cur_bit_n] << l)
                        cur_bit_n += 1
                        l += 1
                    k += 1
                pixels[i, j] = tuple(channels)

                finished_encoding = (cur_bit_n >= self._header_size)
                j += 1
            i += 1

        # Encode message in image
        pixel_order = self._generate_pixel_arrangement(height, width, channel_n, len(msg_bits))
        cur_bit_n = 0
        pixel_n = 0
        finished_encoding = False
        while pixel_n < len(pixel_order) and not finished_encoding:
            i, j = pixel_order[pixel_n][0], pixel_order[pixel_n][1]
            channels = list(pixels[i, j])
            k = 0
            while k < channel_n: 
                l = 0
                channels[k] &= (0b11111111 << self._chan_density)
                while l < self._chan_density and cur_bit_n < len(msg_bits):
                    channels[k] += (msg_bits[cur_bit_n] << l) 
                    cur_bit_n += 1
                    l += 1
                k += 1
            pixels[i, j] = tuple(channels)

            finished_encoding = (cur_bit_n >= len(msg_bits))
            pixel_n += 1
        
        # Save image
        img.save(out_img_path)
        img.close()
        return True
    
    def decode(self, in_img_path: str) -> bytes:
        # Open image file
        img = Image.open(in_img_path)
        pixels = img.load()
        width, height = img.size
        channel_n = len(pixels[0,0])

        # Extract message from image
        msg_bytes = []
        read_bits = 0
        size_header = 0
        i = 0

        # Extract message header
        i = 0
        while i < height and read_bits < self._header_size:
            j = 0
            while j < width and read_bits < self._header_size:
                channels = pixels[i, j] 
                k = 0
                while k < channel_n and read_bits < self._header_size:
                    l = 0
                    while l < self._chan_density and read_bits < self._header_size:
                        bit = (channels[k] >> l) & 1
                        size_header += (bit << read_bits)
                        read_bits += 1
                        l += 1
                    k += 1
                j += 1
            i += 1


        # Extract message
        pixel_order = self._generate_pixel_arrangement(height, width, channel_n, size_header * 8)
        read_bits = 0
        cur_byte = 0
        cur_byte_idx = 0
        pixel_n = 0
        finished_decoding = False
        while pixel_n < len(pixel_order) and not finished_decoding:
            i, j = pixel_order[pixel_n][0], pixel_order[pixel_n][1]
            channels = pixels[i, j]
            k = 0
            while k < channel_n: 
                l = 0
                while l < self._chan_density and read_bits < size_header * 8:
                    bit = (channels[k] >> l) & 1
                    cur_byte += (bit << cur_byte_idx)
                    cur_byte_idx += 1

                    if cur_byte_idx >= 8:
                        msg_bytes.append(cur_byte)
                        cur_byte_idx = 0
                        cur_byte = 0
                    read_bits += 1
                    l += 1
                k += 1
            finished_decoding = (read_bits >= size_header * 8)
            pixel_n += 1
        img.close()
        
        # Convert byte list into bytes object 
        return bytes(msg_bytes)

    def _bytes_to_bitstring(self, msg: bytes) -> list[int]:
        bitstring = []
        for byte in msg:
            bitstring += self._int_to_bitstring(int(byte), 8)
        return bitstring

    def _int_to_bitstring(self, num: int, bitstring_len: int) -> list[int]:
        if num.bit_length() > bitstring_len: 
            return None
        
        bit_s = bin(num).split('b')[1][::-1]
        bits = [0 for i in range(bitstring_len)]
        for i in range(len(bit_s)):
            if bit_s[i] == '1':
                bits[i] = 1
        return bits
    
    # Generates pixel indices for encoding/decoding. Uses self.key for pixel rearrangement if provided
    def _generate_pixel_arrangement(self, width: int, height: int, channels: int, m_len: int) -> list[tuple]:
        header_pixels = int(math.ceil(self._header_size / (self._chan_density * channels)))
        starting_row = header_pixels // width
        starting_col = header_pixels % width

        total_pixels = int(math.ceil((m_len * 8) / (self._chan_density * channels))) 
        arrangement = []
        if self._key is not None:
            start_num = (starting_row * width) + starting_col
            end_num = width * height

            rng = self._generate_csprng(m_len)
            distincts = self._generate_n_distinct(start_num, end_num, total_pixels, rng)

            for num in distincts:
                row = num // width
                col = num % width
                arrangement.append((row, col))
        else:
            i, j = starting_row, starting_col
            while i < height and len(arrangement) < total_pixels:
                while j < width and len(arrangement) < total_pixels:
                    arrangement.append((i, j))
                    j += 1
                i += 1
                j = 0
        return arrangement
    
    # Derives 256 32-bit integers as seed vector for Isaac CSPRNG from the input key and message length
    def _generate_csprng(self, m_len: int) -> Isaac:
        seed_vec = []
        k_idx = 0
        while len(seed_vec) < 256:
            seed_vec.append(((self._key[k_idx] + len(seed_vec))**m_len) % 2**32)
            k_idx = (k_idx + 1) % len(self._key)
        
        rng = Isaac(seed_vec)
        return rng

    # Generates n numbers between start and end, none of which are the same
    def _generate_n_distinct(self, start: int, end: int, num: int, rng: Isaac) -> list[int]:
        numbers = []
        while len(numbers) < num:
            value = int((rng.rand(end)/end) * (end - start) + start) 
            while value in numbers:
                value = (value + 1) % end
                if value < start: 
                    value = start
            numbers.append(value)
        return numbers

