"""Validated, request-owned MP4/WebM file sources for browser understanding."""
import asyncio
import base64
import binascii
from contextlib import asynccontextmanager
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit
from .config import BASE_DIR, TEMP_UPLOADS_DIR, MAX_VIDEO_BYTES, MAX_VIDEOS, MAX_VIDEO_PIXELS
from .errors import GatewayError
from .files import safe_filename
from .images import _fetch_https

FORMATS = {
    '.mp4': ('mov', 'video/mp4'), '.webm': ('matroska', 'video/webm'),
    '.mov': ('mov', 'video/quicktime'), '.m4v': ('mov', 'video/x-m4v'),
    '.mpeg': ('mpeg', 'video/mpeg'), '.mpg': ('mpeg', 'video/mpeg'),
    '.avi': ('avi', 'video/x-msvideo'), '.flv': ('flv', 'video/x-flv'),
    '.wmv': ('asf', 'video/x-ms-wmv'), '.3gp': ('mov', 'video/3gpp'),
    '.3g2': ('mov', 'video/3gpp2'), '.mkv': ('matroska', 'video/x-matroska'),
}
MIME_ALIASES = {'video/avi':'video/x-msvideo', 'video/wmv':'video/x-ms-wmv', 'video/mpg':'video/mpeg', 'video/3gp':'video/3gpp', 'video/m4v':'video/x-m4v'}


def _filename(source):
    name = source.get('filename')
    if name is None and isinstance(source.get('file_url'), str):
        try:
            name = Path(urlsplit(source['file_url']).path).name
        except ValueError:
            pass
    return name


def is_video_source(source):
    if not isinstance(source, dict):
        return False
    name = _filename(source)
    data = source.get('file_data')
    return (isinstance(name, str) and Path(name).suffix.lower() in FORMATS) or (isinstance(data, str) and data.startswith('data:video/'))


def _write_source(source, path):
    safe_filename(_filename(source), FORMATS)
    selected = [key for key in ('file_data', 'file_url', 'file_id') if source.get(key) is not None]
    if len(selected) != 1 or set(source) - {'filename', 'file_data', 'file_url', 'file_id'}:
        raise GatewayError(400, 'Video requires exactly one inline or public URL source.', 'invalid_video')
    value = source[selected[0]]
    if selected[0] == 'file_id':
        raise GatewayError(400, 'Stored video IDs are not implemented.', 'unsupported_capability')
    if not isinstance(value, str) or not value:
        raise GatewayError(400, 'Video source must be nonempty text.', 'invalid_video')
    extension = Path(_filename(source)).suffix.lower()
    if selected[0] == 'file_url':
        data = _fetch_https(value, max_bytes=MAX_VIDEO_BYTES, accept=FORMATS[extension][1], kind='video')
    else:
        if value.startswith('data:'):
            prefix, separator, value = value.partition(',')
            mime = prefix[5:-7] if prefix.startswith('data:') and prefix.endswith(';base64') else ''
            mime = MIME_ALIASES.get(mime, mime)
            if not separator or mime not in (FORMATS[extension][1], 'application/octet-stream'):
                raise GatewayError(400, 'Video data MIME must match its filename.', 'invalid_video')
        if len(value) > 4*((MAX_VIDEO_BYTES+2)//3):
            raise GatewayError(413, 'Video exceeds the configured byte limit.', 'video_too_large')
        try:
            data = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error):
            raise GatewayError(400, 'Invalid base64 video.', 'invalid_video') from None
    if len(data) > MAX_VIDEO_BYTES:
        raise GatewayError(413, 'Video exceeds the configured byte limit.', 'video_too_large')
    if not data:
        raise GatewayError(400, 'Video is empty.', 'invalid_video')
    path = path.with_suffix(extension)
    path.write_bytes(data)
    return str(path)


async def validate_video(path):
    family = FORMATS[Path(path).suffix][0]
    process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'virel.video_validation', str(path), family, str(MAX_VIDEO_PIXELS),
        cwd=BASE_DIR, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    try:
        code = await asyncio.wait_for(process.wait(), timeout=15)
    except (asyncio.CancelledError, asyncio.TimeoutError) as error:
        if process.returncode is None:
            process.kill()
        await process.wait()
        if isinstance(error, asyncio.CancelledError):
            raise
        raise GatewayError(400, 'Video validation exceeded the processing deadline.', 'invalid_video') from None
    if code == 2:
        raise GatewayError(413, 'Video frame exceeds the configured pixel limit.', 'video_too_large')
    if code:
        raise GatewayError(400, 'Video is corrupt, unsupported or has invalid streams.', 'invalid_video')


@asynccontextmanager
async def prepared_videos(sources):
    if len(sources) > MAX_VIDEOS:
        raise GatewayError(413, 'Too many videos for one request.', 'too_many_videos')
    if not sources:
        yield []
        return
    Path(TEMP_UPLOADS_DIR).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='request-', dir=TEMP_UPLOADS_DIR) as folder:
        worker = asyncio.create_task(asyncio.to_thread(lambda: [_write_source(source, Path(folder)/str(index)) for index, source in enumerate(sources)]))
        try:
            paths = await asyncio.shield(worker)
        except asyncio.CancelledError:
            try:
                await worker
            except Exception:
                pass
            raise
        for path in paths:
            await validate_video(path)
        yield paths
