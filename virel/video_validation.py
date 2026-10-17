"""Sample a video in an isolated, killable decoder; never follow external references."""
import sys
import av
from .audio_validation import deny_external


def main(path, expected, max_pixels):
    try:
        with open(path, 'rb') as source, av.open(source, mode='r', options={
                'format_whitelist': 'mov,matroska,webm,mpeg,avi,flv,asf', 'protocol_whitelist': 'file',
                'max_streams': '2', 'max_pixels': str(max_pixels)}, io_open=deny_external) as media:
            if expected not in media.format.name.split(',') or len(media.streams.video) != 1 or len(media.streams.audio) > 1:
                return 1
            if any(stream.type not in ('video', 'audio') for stream in media.streams):
                return 1
            stream = media.streams.video[0]
            if stream.disposition & av.stream.Disposition.attached_pic:
                return 1
            codec = stream.codec_context
            if codec.width < 1 or codec.height < 1:
                return 1
            if codec.width * codec.height > max_pixels:
                return 2
            codec.thread_count = 1
            codec.options = {**codec.options, 'max_pixels': str(max_pixels)}
            frame = next(media.decode(video=0), None)
            if frame is None or frame.width < 1 or frame.height < 1:
                return 1
            return 0 if frame.width * frame.height <= max_pixels else 2
    except Exception:
        return 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1], sys.argv[2], int(sys.argv[3])))
