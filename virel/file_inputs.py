"""Shared native file inputs: bounded sources, validation and request-owned paths."""
import asyncio
import base64
import binascii
from contextlib import AsyncExitStack, asynccontextmanager
import mimetypes
import psutil
import re
from pathlib import Path
import sys
import tempfile
from urllib.parse import unquote, urlsplit
from . import files, images, audio, video
from .config import BASE_DIR, TEMP_UPLOADS_DIR, MAX_FILE_BYTES, MAX_FILE_INPUTS, MAX_DOCUMENT_MEMORY_BYTES
from .document_text import DOCUMENT_EXTENSIONS, TEXT_EXTENSIONS
from .errors import GatewayError

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif'}
SUPPORTED_EXTENSIONS = DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS | set(audio.FORMATS) | set(video.FORMATS) | {'.pdf'}
GENERIC_MIMES = {'application/octet-stream', 'binary/octet-stream', ''}
TEXT_MIMES = {'application/json', 'application/xml', 'application/javascript', 'application/x-javascript', 'application/x-yaml', 'application/yaml', 'application/ndjson', 'application/x-ndjson', 'image/svg+xml'}

def normalize_mime(value):
    if not isinstance(value, str):
        raise GatewayError(400, 'File MIME must be text.', 'invalid_file')
    value = value.split(';', 1)[0].strip().lower()
    if value and (len(value) > 127 or not re.fullmatch(r'[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+', value)):
        raise GatewayError(400, 'Malformed file MIME.', 'invalid_file')
    return value

def mime_for(name):
    return (mimetypes.guess_type(name)[0] or 'application/octet-stream').lower()

def _load(source):
    if not isinstance(source, dict) or set(source) - {'filename','file_data','file_url','file_id'}:
        raise GatewayError(400, 'Invalid file source.', 'invalid_file')
    keys = [k for k in ('file_data','file_url','file_id') if source.get(k) is not None]
    if len(keys) != 1 or not isinstance(source[keys[0]], str) or not source[keys[0]]:
        raise GatewayError(400, 'File requires exactly one nonempty data, URL or ID source.', 'invalid_file')
    if keys[0] == 'file_id':
        item, data = files.read_stored(source['file_id'])
        return data, item['filename'], normalize_mime(item.get('mime_type', mime_for(item['filename'])))
    name = source.get('filename')
    if name is None and keys[0] == 'file_url':
        try:
            name = unquote(Path(urlsplit(source['file_url']).path).name)
        except ValueError:
            raise GatewayError(400, 'Malformed file URL.', 'invalid_file') from None
    if name is None and keys[0] == 'file_data':
        value = source['file_data']
        inferred_ext = '.bin'
        if value.startswith('data:'):
            header, _, _ = value.partition(',')
            mime_part = header[5:].split(';')[0].strip().lower()
            for ext, (_, mimes) in audio.FORMATS.items():
                if mime_part in mimes:
                    inferred_ext = ext
                    break
            else:
                if 'pdf' in mime_part: inferred_ext = '.pdf'
                elif 'png' in mime_part: inferred_ext = '.png'
                elif 'jpeg' in mime_part or 'jpg' in mime_part: inferred_ext = '.jpg'
                elif 'webp' in mime_part: inferred_ext = '.webp'
                elif 'mp4' in mime_part: inferred_ext = '.mp4'
                elif 'ogg' in mime_part: inferred_ext = '.ogg'
                else: inferred_ext = mimetypes.guess_extension(mime_part) or '.bin'
        name = f'attachment{inferred_ext}'
    files.safe_filename(name, SUPPORTED_EXTENSIONS)
    if keys[0] == 'file_url':
        data = files._fetch_https(source['file_url'], max_bytes=MAX_FILE_BYTES, accept='*/*', kind='file')
        mime = mime_for(name)
    else:
        value = source['file_data']; mime = mime_for(name)
        if value.startswith('data:'):
            header, separator, value = value.partition(',')
            if not separator or not header.endswith(';base64'):
                raise GatewayError(400, 'File data URI requires base64.', 'invalid_file')
            mime = header[5:-7].lower()
        if len(value) > 4*((MAX_FILE_BYTES+2)//3):
            raise GatewayError(413, 'File exceeds VIREL_MAX_FILE_MB.', 'file_too_large')
        try:
            data = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error):
            raise GatewayError(400, 'Invalid base64 file.', 'invalid_file') from None
    if not data or len(data) > MAX_FILE_BYTES:
        raise GatewayError(413 if data else 400, 'File is empty or exceeds VIREL_MAX_FILE_MB.', 'file_too_large' if data else 'invalid_file')
    return data, name, normalize_mime(mime)

async def _extract(path, output):
    process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'virel.document_text', str(path), str(output),
        cwd=BASE_DIR, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    waiter = asyncio.create_task(process.wait())
    try:
        async with asyncio.timeout(15):
            while not waiter.done():
                done, _ = await asyncio.wait({waiter}, timeout=.05)
                if not done:
                    try:
                        if psutil.Process(process.pid).memory_info().rss > MAX_DOCUMENT_MEMORY_BYTES:
                            raise GatewayError(413, 'Document parser exceeds VIREL_MAX_DOCUMENT_MEMORY_MB.', 'file_too_large')
                    except psutil.NoSuchProcess:
                        pass
                    except psutil.AccessDenied:
                        raise GatewayError(503, 'Document parser memory guard is unavailable.', 'file_processing_unavailable') from None
            code = await waiter
    except (asyncio.CancelledError, asyncio.TimeoutError, GatewayError) as error:
        if process.returncode is None:
            process.kill()
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        await process.wait()
        if isinstance(error, (asyncio.CancelledError, GatewayError)):
            raise
        raise GatewayError(400, 'Document parser exceeded its deadline.', 'invalid_file') from None
    if code:
        raise GatewayError(413 if code == 2 else 400, 'Document exceeds extraction limits; nothing was truncated.' if code == 2 else 'Document is corrupt, encrypted, empty or has no extractable text. Use PDF for scanned/visual content.', 'file_too_large' if code == 2 else 'invalid_file')

def _check_document_mime(name, mime):
    extension = Path(name).suffix.lower()
    if mime in GENERIC_MIMES:
        return
    if extension in TEXT_EXTENSIONS:
        valid = mime.startswith('text/') or mime in TEXT_MIMES or mime == mime_for(name)
    else:
        valid = mime == mime_for(name) or mime in {'application/zip','application/x-zip-compressed'} and extension != '.rtf'
        if extension == '.rtf':
            valid |= mime in {'application/rtf', 'text/rtf'}
    if not valid:
        raise GatewayError(400, 'File MIME does not match its document type.', 'invalid_file')

@asynccontextmanager
async def prepared_file_inputs(sources):
    if len(sources) > MAX_FILE_INPUTS:
        sources = sources[-MAX_FILE_INPUTS:]
    if not sources:
        yield []
        return
    Path(TEMP_UPLOADS_DIR).mkdir(parents=True, exist_ok=True)
    async with AsyncExitStack() as stack:
        folder = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='request-', dir=TEMP_UPLOADS_DIR)))
        paths = []; counts = {'pdf':0, 'video':0}
        for index, source in enumerate(sources):
            worker = asyncio.create_task(asyncio.to_thread(_load, source))
            try:
                data, name, mime = await asyncio.shield(worker)
            except asyncio.CancelledError:
                try:
                    await worker
                except Exception:
                    pass
                raise
            extension = Path(name).suffix.lower()
            if extension == '.pdf':
                if mime not in GENERIC_MIMES | {'application/pdf'}:
                    raise GatewayError(400, 'PDF MIME does not match content.', 'invalid_file')
                counts['pdf'] += 1
                if counts['pdf'] > files.MAX_PDFS:
                    raise GatewayError(413, 'Too many PDFs.', 'too_many_files')
                encoded = base64.b64encode(data).decode()
                prepared = await stack.enter_async_context(files.prepared_pdfs([{'filename':name,'file_data':encoded}]))
                paths.extend(prepared)
            elif extension in IMAGE_EXTENSIONS:
                declared = None if mime in GENERIC_MIMES else {'image/jpg':'image/jpeg'}.get(mime,mime)
                fmt, _ = images.validate_image_bytes(data, declared)
                output = folder / (str(index) + images.FORMATS[fmt][1])
                if fmt == 'GIF':
                    from PIL import Image
                    import io
                    output = folder / (str(index) + '.png')
                    with Image.open(io.BytesIO(data)) as picture:
                        picture.convert('RGBA').save(output, format='PNG')
                else:
                    output.write_bytes(data)
                paths.append(str(output))
            elif extension in audio.FORMATS and (extension not in video.FORMATS or mime.startswith('audio/')):
                path = await stack.enter_async_context(audio.prepared_audio(data,name,None if mime in GENERIC_MIMES else mime))
                paths.append(path)
            elif extension in video.FORMATS:
                counts['video'] += 1
                if counts['video'] > video.MAX_VIDEOS:
                    raise GatewayError(413, 'Too many videos.', 'too_many_videos')
                encoded = base64.b64encode(data).decode()
                declared = 'application/octet-stream' if mime in GENERIC_MIMES else mime
                prepared = await stack.enter_async_context(video.prepared_videos([{'filename':name,'file_data':'data:'+declared+';base64,'+encoded}]))
                paths.extend(prepared)
            elif extension in DOCUMENT_EXTENSIONS:
                _check_document_mime(name,mime)
                subfolder = folder / str(index); subfolder.mkdir()
                original = subfolder / name; original.write_bytes(data)
                output = subfolder / (name + '.txt')
                await _extract(original, output)
                paths.append(str(output))
            else:
                raise GatewayError(400, 'Unsupported file type.', 'unsupported_file')
        yield paths
