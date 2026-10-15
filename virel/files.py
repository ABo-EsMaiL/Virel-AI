"""Validated PDF sources, private expiring file IDs and request copies."""
import asyncio
import base64
import binascii
from contextlib import asynccontextmanager
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import threading
import time
import uuid
from .config import API_KEY, BASE_DIR, RUNTIME_DIR, TEMP_UPLOADS_DIR, MAX_PDF_BYTES, MAX_PDF_PAGES, MAX_PDFS
from .errors import GatewayError
from .images import _fetch_https

MAX_STORED_FILES = 20
MAX_STORED_BYTES = 100 * 1024 * 1024
FILE_TTL = 3600
FILES_DIR = Path(RUNTIME_DIR) / 'files'
_store_lock = threading.RLock()
_ID = re.compile(r'file-[a-f0-9]{32}')


def require_file_key():
    if not API_KEY:
        raise GatewayError(503, 'Configure VIREL_API_KEY before using uploaded file IDs.', 'file_store_unavailable')


def safe_filename(name, suffixes=(".pdf",)):
    if not isinstance(name, str) or not name or len(name) > 120 or name in ('.', '..') or any(ord(c) < 32 or ord(c) == 127 for c in name) or any(c in name for c in '/\\:') or not name.lower().endswith(tuple(suffixes)):
        raise GatewayError(400, 'Use a supported filename without paths or control characters.', 'invalid_file')
    return name


async def validate_pdf(path):
    if Path(path).stat().st_size > MAX_PDF_BYTES:
        raise GatewayError(413, f'PDF exceeds the {MAX_PDF_BYTES // (1024*1024)} MiB limit.', 'file_too_large')
    with open(path, 'rb') as source:
        header = source.read(5)
    if header != b'%PDF-':
        raise GatewayError(400, 'File must contain a valid PDF.', 'invalid_file')
    process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'virel.pdf_validation', str(path), str(MAX_PDF_PAGES), str(MAX_PDF_BYTES),
        cwd=BASE_DIR, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    try:
        code = await asyncio.wait_for(process.wait(), timeout=10)
    except asyncio.CancelledError:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    except asyncio.TimeoutError:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise GatewayError(400, 'PDF validation exceeded the allowed processing time.', 'invalid_file') from None
    if code == 3:
        raise GatewayError(413, f'PDF must contain between 1 and {MAX_PDF_PAGES} pages.', 'file_page_limit')
    if code:
        message = 'Encrypted PDFs are not supported.' if code == 2 else 'PDF structure is corrupt or unsupported.'
        raise GatewayError(400, message, 'invalid_file')


def _folder(file_id):
    if not isinstance(file_id, str) or not _ID.fullmatch(file_id):
        raise GatewayError(404, 'File not found or expired.', 'file_not_found')
    return Path(FILES_DIR) / file_id


def _metadata(folder):
    try:
        path = folder / 'metadata.json'
        if folder.is_symlink() or path.stat().st_size > 4096:
            raise ValueError()
        item = json.loads(path.read_text(encoding='utf-8'))
        if item['id'] != folder.name or not isinstance(item['expires_at'], int) or not isinstance(item['bytes'], int) or not (folder/'data.pdf').is_file():
            raise ValueError()
        return item
    except (OSError, ValueError, KeyError, TypeError):
        return None


def prune_files():
    with _store_lock:
        root = Path(FILES_DIR)
        if not root.exists():
            return
        for folder in root.iterdir():
            if not folder.is_dir() or folder.is_symlink() or not folder.resolve().is_relative_to(root.resolve()):
                continue
            if folder.name.startswith('upload-'):
                shutil.rmtree(folder)
            elif _ID.fullmatch(folder.name):
                item = _metadata(folder)
                if not item or item['expires_at'] <= time.time():
                    shutil.rmtree(folder)


def list_stored():
    require_file_key()
    with _store_lock:
        prune_files()
        root = Path(FILES_DIR)
        return sorted([item for folder in root.glob('file-*') if (item := _metadata(folder))], key=lambda item: item['created_at'], reverse=True)


def read_stored(file_id):
    require_file_key()
    with _store_lock:
        prune_files()
        folder = _folder(file_id)
        item = _metadata(folder)
        if not item:
            raise GatewayError(404, 'File not found or expired.', 'file_not_found')
        data = (folder/'data.pdf').read_bytes()
        if len(data) != item['bytes'] or len(data) > MAX_PDF_BYTES:
            raise GatewayError(400, 'Stored PDF is invalid.', 'invalid_file')
        return item, data


def delete_stored(file_id):
    with _store_lock:
        item, _ = read_stored(file_id)
        folder = _folder(file_id)
        if folder.is_symlink() or not folder.resolve().is_relative_to(Path(FILES_DIR).resolve()):
            raise GatewayError(404, 'File not found or expired.', 'file_not_found')
        shutil.rmtree(folder)
        return {'id': item['id'], 'object': 'file', 'deleted': True}


async def save_uploaded(data, filename, purpose):
    require_file_key()
    filename = safe_filename(filename)
    if purpose not in ('user_data', 'assistants'):
        raise GatewayError(400, 'PDF uploads accept user_data or assistants purpose.', 'unsupported_capability')
    if len(data) > MAX_PDF_BYTES:
        raise GatewayError(413, f'PDF exceeds the {MAX_PDF_BYTES // (1024*1024)} MiB limit.', 'file_too_large')
    Path(TEMP_UPLOADS_DIR).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='request-', dir=TEMP_UPLOADS_DIR) as tmp:
        path = Path(tmp)/'upload.pdf'
        path.write_bytes(data)
        await validate_pdf(path)
        with _store_lock:
            current = list_stored()
            if len(current) >= MAX_STORED_FILES or sum(item['bytes'] for item in current) + len(data) > MAX_STORED_BYTES:
                raise GatewayError(413, 'Uploaded file storage quota exceeded. Delete old files.', 'file_storage_limit')
            now = int(time.time())
            item = {'id': 'file-'+uuid.uuid4().hex, 'object': 'file', 'bytes': len(data), 'created_at': now,
                'filename': filename, 'purpose': purpose, 'expires_at': now+FILE_TTL}
            root = Path(FILES_DIR)
            root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='upload-', dir=root) as staging:
                folder = Path(staging)
                (folder/'data.pdf').write_bytes(data)
                (folder/'metadata.json').write_text(json.dumps(item), encoding='utf-8')
                folder.rename(root/item['id'])
            return item


def _write_source(source, path):
    if not isinstance(source, dict):
        raise GatewayError(400, 'PDF source must be an object.', 'invalid_file')
    allowed = ('file_data', 'file_url', 'file_id')
    selected = [name for name in allowed if source.get(name) is not None]
    if len(selected) != 1 or any(name not in (*allowed, 'filename') for name in source):
        raise GatewayError(400, 'PDF requires exactly one supported source.', 'invalid_file')
    value = source[selected[0]]
    if not isinstance(value, str) or not value:
        raise GatewayError(400, 'PDF source must be nonempty text.', 'invalid_file')
    if selected[0] == 'file_id':
        _, data = read_stored(value)
    elif selected[0] == 'file_url':
        data = _fetch_https(value, max_bytes=MAX_PDF_BYTES, accept='application/pdf', kind='file')
    else:
        safe_filename(source.get('filename'))
        encoded = value
        if value.startswith('data:'):
            prefix = 'data:application/pdf;base64,'
            if not value.startswith(prefix):
                raise GatewayError(400, 'PDF data URI must declare application/pdf base64.', 'invalid_file')
            encoded = value[len(prefix):]
        if len(encoded) > 4*((MAX_PDF_BYTES+2)//3):
            raise GatewayError(413, f'PDF exceeds the {MAX_PDF_BYTES // (1024*1024)} MiB limit.', 'file_too_large')
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise GatewayError(400, 'Invalid base64 PDF.', 'invalid_file') from None
    if len(data) > MAX_PDF_BYTES:
        raise GatewayError(413, f'PDF exceeds the {MAX_PDF_BYTES // (1024*1024)} MiB limit.', 'file_too_large')
    path.write_bytes(data)
    return str(path)


@asynccontextmanager
async def prepared_pdfs(sources):
    if len(sources) > MAX_PDFS:
        raise GatewayError(413, f'At most {MAX_PDFS} PDFs are accepted per request.', 'too_many_files')
    if not sources:
        yield []
        return
    Path(TEMP_UPLOADS_DIR).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='request-', dir=TEMP_UPLOADS_DIR) as folder:
        worker = asyncio.create_task(asyncio.to_thread(lambda: [_write_source(source, Path(folder)/(str(index)+'.pdf')) for index, source in enumerate(sources, 1)]))
        try:
            paths = await asyncio.shield(worker)
        except asyncio.CancelledError:
            try:
                await worker
            except Exception:
                pass
            raise
        for path in paths:
            await validate_pdf(path)
        yield paths


async def expiry_loop():
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(prune_files)
        except OSError:
            # Retry next pass without leaking filesystem paths into logs.
            pass
