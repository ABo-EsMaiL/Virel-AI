"""Validated image sources and request-owned upload lifetime."""
import asyncio
import base64
import binascii
from contextlib import asynccontextmanager
import http.client
import io
import ipaddress
from pathlib import Path
import re
import socket
import tempfile
import time
from urllib.parse import urlsplit, quote
from PIL import Image, UnidentifiedImageError
from .config import TEMP_UPLOADS_DIR
from .errors import GatewayError

MAX_IMAGES = 4
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_REQUEST_BYTES = 32 * 1024 * 1024
FORMATS = {'PNG': ('image/png', '.png'), 'JPEG': ('image/jpeg', '.jpg'), 'WEBP': ('image/webp', '.webp')}

class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, timeout=5)
        self.address = address

    def connect(self):
        raw = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise

def _fetch_https(url, *, max_bytes=None, accept="image/png,image/jpeg,image/webp", kind="image"):
    max_bytes = MAX_IMAGE_BYTES if max_bytes is None else max_bytes
    if not isinstance(url, str) or any(ord(char) < 33 or ord(char) == 127 for char in url):
        raise GatewayError(400, 'Invalid public media URL.', 'invalid_'+kind+'_url')
    try:
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.fragment or parsed.port not in (None, 443):
            raise ValueError()
        host = parsed.hostname.encode('idna').decode('ascii')
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        addresses = [record[4][0] for record in records]
        if not addresses or any(not ipaddress.ip_address(address).is_global or ipaddress.ip_address(address).is_multicast for address in addresses):
            raise ValueError()
    except (ValueError, OSError, UnicodeError):
        raise GatewayError(400, 'Only public HTTPS media URLs on port 443 are accepted.', 'invalid_'+kind+'_url') from None
    connection = _PinnedHTTPSConnection(host, addresses[0])
    try:
        started = time.monotonic()
        target = quote(parsed.path or '/', safe='/%:@!$&()*+,;=-._~')
        if parsed.query:
            target += '?' + quote(parsed.query, safe='/%:@!$&()*+,;=?-._~')
        connection.request('GET', target, headers={'Accept': accept, 'User-Agent': 'Virel-AI'})
        response = connection.getresponse()
        if 300 <= response.status < 400:
            raise GatewayError(400, 'Media URL must return the media directly without redirects.', 'invalid_'+kind+'_url')
        if response.status != 200:
            raise GatewayError(502, 'The public media server could not return the media.', kind+'_fetch_failed')
        length = response.getheader('Content-Length')
        if length is not None and int(length) > max_bytes:
            raise GatewayError(413, 'Media exceeds its byte limit.', kind+'_too_large')
        parts, total = [], 0
        while True:
            if time.monotonic() - started > 20:
                raise TimeoutError()
            chunk = response.read1(min(65536, max_bytes - total + 1))
            if not chunk:
                return b''.join(parts)
            total += len(chunk)
            if total > max_bytes:
                raise GatewayError(413, 'Media exceeds its byte limit.', kind+'_too_large')
            parts.append(chunk)
    except GatewayError:
        raise
    except (OSError, http.client.HTTPException, ValueError):
        raise GatewayError(502, 'Could not fetch the public media within the allowed limits.', kind+'_fetch_failed') from None
    finally:
        connection.close()

def _prepare_one(source, folder, index):
    declared_mime = None
    if not isinstance(source, str) or not source:
        raise GatewayError(400, 'An image URL or data image is required.', 'invalid_image')
    if source.startswith('data:'):
        match = re.fullmatch(r'data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=]+)', source)
        if not match:
            raise GatewayError(400, 'Use a valid PNG, JPEG or WebP base64 data image.', 'invalid_image')
        declared_mime, encoded = match.groups()
        if len(encoded) > 4 * ((MAX_IMAGE_BYTES + 2) // 3):
            raise GatewayError(413, 'Image exceeds the 5 MiB limit.', 'image_too_large')
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise GatewayError(400, 'Invalid base64 image.', 'invalid_image') from None
    else:
        data = _fetch_https(source)
    if len(data) > MAX_IMAGE_BYTES:
        raise GatewayError(413, 'Image exceeds the 5 MiB limit.', 'image_too_large')
    try:
        with Image.open(io.BytesIO(data), formats=list(FORMATS)) as image:
            fmt = image.format
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise GatewayError(413, 'Image exceeds the 20 million pixel limit.', 'image_too_large')
            if getattr(image, 'n_frames', 1) != 1:
                raise GatewayError(400, 'Animated images are not supported in this stage.', 'unsupported_image')
            if declared_mime and declared_mime != FORMATS[fmt][0]:
                raise GatewayError(400, 'Declared image MIME does not match its content.', 'invalid_image')
            image.verify()
        with Image.open(io.BytesIO(data), formats=[fmt]) as image:
            image.load()
    except GatewayError:
        raise
    except Image.DecompressionBombError:
        raise GatewayError(413, 'Image exceeds the pixel limit.', 'image_too_large') from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise GatewayError(400, 'Image content is corrupt or unsupported.', 'invalid_image') from None
    path = Path(folder) / (str(index) + FORMATS[fmt][1])
    path.write_bytes(data)
    return str(path)

@asynccontextmanager
async def prepared_images(sources):
    if len(sources) > MAX_IMAGES:
        raise GatewayError(413, 'At most four images are accepted per request.', 'too_many_images')
    if not sources:
        yield []
        return
    Path(TEMP_UPLOADS_DIR).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='request-', dir=TEMP_UPLOADS_DIR) as folder:
        def prepare():
            return [_prepare_one(source, folder, index) for index, source in enumerate(sources, 1)]
        worker = asyncio.create_task(asyncio.to_thread(prepare))
        try:
            paths = await asyncio.shield(worker)
        except asyncio.CancelledError:
            # A cancelled await must not remove the directory while its worker still writes.
            try:
                await worker
            except Exception:
                pass
            raise
        yield paths
