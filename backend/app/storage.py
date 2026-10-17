"""Private local upload storage; filenames never come from the client."""
import asyncio
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import tempfile
import time
from uuid import uuid4

MAX_UPLOAD_BYTES = 200 * 1024 * 1024


class IntakeError(ValueError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message

    def payload(self):
        return {'error': {'code': self.code, 'message': self.message, 'status': self.status}}


@dataclass(frozen=True)
class StagedUpload:
    path: Path
    size_bytes: int
    sha256: str


class LocalStorage:
    def __init__(self, root: Path, *, max_bytes: int = MAX_UPLOAD_BYTES):
        root = Path(root)
        if not root.is_absolute() or not 0 < max_bytes <= MAX_UPLOAD_BYTES:
            raise ValueError('Absolute runtime root and a valid upload limit required')
        self.root = root.resolve()
        if any((parent / '.git').exists() for parent in [self.root, *self.root.parents]):
            raise ValueError('Runtime storage must be outside the Git checkout')
        self.max_bytes = max_bytes
        self.incoming, self.originals = self.root / 'incoming', self.root / 'originals'
        for path in [self.root, self.incoming, self.originals]:
            if path.is_symlink():
                raise ValueError('Runtime subdirectories must not be symlinks')
            path.mkdir(mode=0o700, parents=True, exist_ok=True)

    def discard(self, path: Path) -> None:
        path = Path(path)
        if path.parent not in (self.incoming, self.originals) or path.is_symlink():
            raise ValueError('Not an owned upload path')
        path.unlink(missing_ok=True)

    async def spool(self, upload, *, deadline_monotonic: float) -> StagedUpload:
        path = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.incoming, prefix='upload-', suffix='.part', delete=False) as target:
                path = Path(target.name)
                digest, size = hashlib.sha256(), 0
                while True:
                    remaining = deadline_monotonic - time.monotonic()
                    if remaining <= 0:
                        raise IntakeError(400, 'invalid_request', 'Upload time budget exceeded.')
                    chunk = await asyncio.wait_for(upload.read(64 * 1024), timeout=remaining)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise IntakeError(413, 'upload_too_large', 'Upload exceeds the byte limit.')
                    target.write(chunk)
                    digest.update(chunk)
                if size == 0:
                    raise IntakeError(400, 'invalid_request', 'An empty file is not a video.')
                target.flush()
                os.fsync(target.fileno())
            return StagedUpload(path, size, digest.hexdigest())
        except BaseException as error:
            if path is not None:
                self.discard(path)
            if isinstance(error, asyncio.TimeoutError):
                raise IntakeError(400, 'invalid_request', 'Upload time budget exceeded.') from None
            if isinstance(error, OSError):
                raise IntakeError(503, 'service_unavailable', 'Upload storage is unavailable.') from None
            raise

    def promote(self, path: Path) -> Path:
        path = Path(path)
        if path.parent != self.incoming or path.is_symlink():
            raise ValueError('Not a staged local upload')
        destination = self.originals / (uuid4().hex + '.video')
        try:
            os.replace(path, destination)
            descriptor = os.open(self.originals, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            return destination
        except OSError:
            self.discard(destination)
            raise IntakeError(503, 'service_unavailable', 'Upload storage is unavailable.') from None
