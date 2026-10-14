"""Bounded structural PDF validation in a killable child process."""
import sys
from pypdf import PdfReader, apply_configuration


def main(path):
    try:
        with apply_configuration(page_tree_maximum_entries=500, page_tree_maximum_depth=20,
                maximum_declared_stream_length=10*1024*1024, zlib_maximum_output_length=16*1024*1024,
                stream_decoding_work_maximum_length=32*1024*1024):
            reader = PdfReader(path, strict=True)
            if reader.is_encrypted:
                return 2
            count = len(reader.pages)
            return 0 if 1 <= count <= 50 else 3
    except Exception:
        return 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1]))
