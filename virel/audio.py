"""Validated, request-owned audio uploads; no local transcription."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import sys
import tempfile
from .config import BASE_DIR, TEMP_UPLOADS_DIR, MAX_AUDIO_BYTES
from .errors import GatewayError
from .files import safe_filename

FORMATS = {
    '.wav': ('wav', {'audio/wav', 'audio/x-wav', 'audio/wave'}),
    '.mp3': ('mp3', {'audio/mpeg', 'audio/mp3'}),
    '.mpga': ('mp3', {'audio/mpeg'}),
    '.mpeg': ('mp3', {'audio/mpeg'}),
    '.m4a': ('mov', {'audio/mp4', 'audio/m4a', 'audio/x-m4a'}),
    '.mp4': ('mov', {'audio/mp4', 'video/mp4'}),
    '.ogg': ('ogg', {'audio/ogg', 'application/ogg'}),
    '.flac': ('flac', {'audio/flac', 'audio/x-flac'}),
    '.webm': ('matroska', {'audio/webm', 'video/webm'}),
    '.weba': ('matroska', {'audio/webm'}),
    '.oga': ('ogg', {'audio/ogg', 'application/ogg'}),
    '.opus': ('ogg', {'audio/ogg', 'audio/opus'}),
    '.aac': ('aac', {'audio/aac', 'audio/x-aac'}),
    '.aiff': ('aiff', {'audio/aiff', 'audio/x-aiff'}),
    '.aif': ('aiff', {'audio/aiff', 'audio/x-aiff'}),
    '.m4b': ('mov', {'audio/mp4', 'audio/x-m4b'}),
}


@asynccontextmanager
async def prepared_audio(data, filename, mime):
    safe_filename(filename, FORMATS)
    extension = Path(filename).suffix.lower()
    family, mimes = FORMATS[extension]
    mime = mime.split(';', 1)[0].strip().lower() if isinstance(mime, str) else mime
    if mime not in mimes | {'application/octet-stream', None}:
        raise GatewayError(400, 'Audio MIME does not match the declared file format.', 'invalid_audio')
    if len(data) > MAX_AUDIO_BYTES:
        raise GatewayError(413, 'Audio exceeds the configured byte limit.', 'audio_too_large')
    if not data:
        raise GatewayError(400, 'Audio file is empty.', 'invalid_audio')
    Path(TEMP_UPLOADS_DIR).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='request-', dir=TEMP_UPLOADS_DIR) as folder:
        path = Path(folder)/('audio'+extension)
        path.write_bytes(data)
        process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'virel.audio_validation', str(path), family,
            cwd=BASE_DIR, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            code = await asyncio.wait_for(process.wait(), timeout=15)
        except asyncio.CancelledError:
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise
        except asyncio.TimeoutError:
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise GatewayError(400, 'Audio validation exceeded the processing deadline.', 'invalid_audio') from None
        if code:
            raise GatewayError(400, 'Audio is corrupt, unsupported, or contains non-audio streams.', 'invalid_audio')
        yield str(path)
