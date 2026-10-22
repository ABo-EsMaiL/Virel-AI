"""Bounded structural PDF validation in a killable child process."""
import sys
from pypdf import PdfReader
try:
    from pypdf import apply_configuration
except ImportError:
    from contextlib import contextmanager
    @contextmanager
    def apply_configuration(**kwargs):
        yield


def main(path, max_pages, max_bytes):
    try:
        with apply_configuration(page_tree_maximum_entries=max_pages*4, page_tree_maximum_depth=20,
                maximum_declared_stream_length=max_bytes, zlib_maximum_output_length=16*1024*1024,
                stream_decoding_work_maximum_length=32*1024*1024):
            reader = PdfReader(path, strict=True)
            if reader.is_encrypted:
                return 2
            count = len(reader.pages)
            return 0 if 1 <= count <= max_pages else 3
    except Exception:
        return 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3])))
