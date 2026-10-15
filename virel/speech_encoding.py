"""Bounded, killable file encoding only; never speech synthesis."""
import io
from fractions import Fraction
from pathlib import Path
import sys
import av
from .audio_validation import deny_external

ENCODERS = {
    'mp3': ('mp3', 'libmp3lame', 24000, 's16p'),
    'opus': ('ogg', 'libopus', 48000, 's16'),
    'aac': ('adts', 'aac', 24000, 'fltp'),
    'flac': ('flac', 'flac', 24000, 's16'),
    'wav': ('wav', 'pcm_s16le', 24000, 's16'),
    'pcm': ('s16le', 'pcm_s16le', 24000, 's16'),
}


class AudioLimit(ValueError):
    pass


class BoundedBuffer(io.BytesIO):
    def __init__(self, limit):
        super().__init__()
        self.limit = limit

    def write(self, data):
        if self.tell() + len(data) > self.limit:
            raise AudioLimit('Output byte limit')
        return super().write(data)


def tempo_frames(frames, speed):
    if speed == 1:
        yield from frames
        return
    factors = []
    while speed > 2:
        factors.append(2.0)
        speed /= 2
    while speed < .5:
        factors.append(.5)
        speed /= .5
    factors.append(speed)
    graph = None
    def drain():
        while True:
            try:
                yield sink.pull()
            except (av.error.BlockingIOError, av.error.EOFError):
                return
    for frame in frames:
        if graph is None:
            graph = av.filter.Graph()
            entry = graph.add_abuffer(sample_rate=frame.sample_rate, format=frame.format.name,
                layout=frame.layout.name, time_base=frame.time_base)
            previous = entry
            for factor in factors:
                node = graph.add('atempo', str(factor))
                previous.link_to(node)
                previous = node
            sink = graph.add('abuffersink')
            previous.link_to(sink)
            graph.configure()
        entry.push(frame)
        yield from drain()
    if graph:
        entry.push(None)
        yield from drain()


def encode(source_path, target_path, fmt, speed, max_bytes, max_seconds):
    raw = Path(source_path).read_bytes()
    if not raw or len(raw) > max_bytes:
        raise AudioLimit('Source byte limit')
    with av.open(io.BytesIO(raw), mode='r', format='wav', options={
            'format_whitelist':'wav', 'protocol_whitelist':'file', 'max_streams':'1'}, io_open=deny_external) as media:
        if len(media.streams) != 1 or len(media.streams.audio) != 1 or media.streams.audio[0].codec_context.name != 'pcm_s16le':
            raise ValueError('Expected the observed PCM WAV source')
        samples = 0
        def frames():
            nonlocal samples
            for frame in media.decode(audio=0):
                if frame.sample_rate != 24000 or len(frame.layout.channels) != 1 or frame.format.name != 's16':
                    raise ValueError('Unexpected source sample format')
                samples += frame.samples
                if samples > max_seconds * 24000:
                    raise AudioLimit('Source duration limit')
                yield frame
            if samples <= 2400:
                raise ValueError('No complete speech audio')
        if fmt in ('auto', 'wav') and speed == 1:
            for _ in frames():
                pass
            result = raw
        else:
            mux, codec, rate, sample_format = ENCODERS['wav' if fmt == 'auto' else fmt]
            output = BoundedBuffer(max_bytes)
            with av.open(output, mode='w', format=mux) as target:
                stream = target.add_stream(codec, rate=rate)
                stream.layout = 'mono'
                stream.codec_context.format = sample_format
                if fmt in ('mp3', 'aac', 'opus'):
                    stream.bit_rate = 128000
                resampler = av.AudioResampler(format=sample_format, layout='mono', rate=rate)
                count = 0
                def mux_frames(items):
                    nonlocal count
                    for frame in items:
                        frame.pts = count
                        frame.time_base = Fraction(1, rate)
                        count += frame.samples
                        if count > max_seconds * 4 * rate + rate:
                            raise AudioLimit('Transformed duration limit')
                        for packet in stream.encode(frame):
                            target.mux(packet)
                for frame in tempo_frames(frames(), speed):
                    mux_frames(resampler.resample(frame))
                mux_frames(resampler.resample(None))
                for packet in stream.encode(None):
                    target.mux(packet)
            result = output.getvalue()
    if not result or len(result) > max_bytes:
        raise AudioLimit('Output byte limit')
    Path(target_path).write_bytes(result)


if __name__ == '__main__':
    try:
        encode(sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]))
    except AudioLimit:
        raise SystemExit(2)
    except Exception:
        raise SystemExit(1)
