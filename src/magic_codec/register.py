import codecs
from .codec import find_codec

# registers the magic_codec search function when this module is imported
codecs.register(find_codec)
