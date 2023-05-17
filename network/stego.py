from PIL import Image

class StegoTranscoder:
    def __init__(self, chan_density=2):
        self.header_size = 16
        self.chan_density = chan_density

    # Message should be a 'bytes' object
    def encode(self, message, in_img_path, out_img_path):
        # Load image, calculate image size
        img = Image.open(in_img_path)
        pixels = img.load()
        width, height = img.size
        channel_n = len(pixels[0,0])

        # Check if image sufficient size for message
        encodable_bits = width * height * channel_n * self.chan_density 
        payload_bits = self._bytes_to_bitstring(message)
        msg_bits = self._int_to_bitstring(int(len(payload_bits) / 8), self.header_size) + payload_bits

        if len(msg_bits) > encodable_bits:
            return False

        # Encode message in image
        cur_bit_n = 0
        i = 0
        while i < height: 
            j = 0
            while j < width:
                channels = list(pixels[j, i])
                k = 0
                while k < channel_n: 
                    l = 0
                    channels[k] &= (0b11111111 << self.chan_density)
                    while l < self.chan_density and cur_bit_n < len(msg_bits):
                        channels[k] += (msg_bits[cur_bit_n] << l) 
                        cur_bit_n += 1
                        l += 1
                    k += 1
                pixels[j, i] = tuple(channels)

                if cur_bit_n >= len(msg_bits):
                    i, j = height, width
                j += 1
            i += 1
        
        # Save image
        img.save(out_img_path)
        img.close()
        return True
    
    def decode(self, in_img_path):
        # Open image file
        img = Image.open(in_img_path)
        pixels = img.load()
        width, height = img.size
        channel_n = len(pixels[0,0])

        # Extract message from image
        msg_bytes = []
        read_bits = 0
        header = 0
        i = 0

        cur_byte = 0
        cur_byte_idx = 0
        while i < height:
            j = 0
            while j < width:
                channels = pixels[j, i]
                k = 0
                while k < channel_n:
                    l = 0
                    while l < self.chan_density:
                        bit = (channels[k] >> l) & 1
                        if read_bits < self.header_size:
                            header += (bit << read_bits) 
                        elif read_bits - self.header_size < header * 8:
                            cur_byte += (bit << cur_byte_idx)
                            cur_byte_idx += 1

                            if cur_byte_idx >= 8:
                                msg_bytes.append(cur_byte)
                                cur_byte_idx = 0
                                cur_byte = 0
                        read_bits += 1
                        l += 1
                    k += 1
                if read_bits - self.header_size >= header * 8:
                    j = width
                    i = height
                j += 1
            i += 1
        img.close()
        
        # Convert byte list into bytes object 
        return bytes(msg_bytes)

    def _bytes_to_bitstring(self, msg):
        bitstring = []
        for byte in msg:
            bitstring += self._int_to_bitstring(int(byte), 8)
        return bitstring

    def _int_to_bitstring(self, num, bitstring_len):
        if num.bit_length() > bitstring_len: 
            return None
        
        bit_s = bin(num).split('b')[1][::-1]
        bits = [0 for i in range(bitstring_len)]
        for i in range(len(bit_s)):
            if bit_s[i] == '1':
                bits[i] = 1
        return bits