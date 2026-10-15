"""Decode an audio sample in an isolated, killable validation process."""
import sys
import av


def deny_external(url, flags, options):
    raise ValueError('External media references are unsupported')


def main(path, expected):
    try:
        with open(path, 'rb') as source, av.open(source, mode='r', options={
                'format_whitelist': 'wav,mp3,mov,ogg,flac,matroska,webm',
                'protocol_whitelist': 'file', 'max_streams': '2'}, io_open=deny_external) as media:
            if expected not in media.format.name.split(',') or len(media.streams.audio) != 1:
                return 1
            for stream in media.streams:
                cover = stream.type == 'video' and stream.disposition & av.stream.Disposition.attached_pic
                if stream.type != 'audio' and not cover:
                    return 1
            frame = next(media.decode(audio=0), None)
            return 0 if frame is not None and frame.samples > 0 and frame.sample_rate > 0 else 1
    except Exception:
        return 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
