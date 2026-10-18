"""Bounded local probe and real video-frame decoding with original PTS."""
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import selectors
import subprocess
import time
import threading

from contracts.python_ports import AcceptedUpload, VideoInfo
from .storage import IntakeError, MAX_UPLOAD_BYTES


def _invalid(message='Video cannot be decoded.'):
    return IntakeError(400, 'invalid_request', message)


def _unsupported(message='Unsupported media format or limits.'):
    return IntakeError(415, 'unsupported_media', message)


class VideoValidator:
    def __init__(self, *, ffprobe='ffprobe', timeout_seconds=120, cpu_threads=2):
        self.ffprobe, self.timeout_seconds, self.cpu_threads = ffprobe, timeout_seconds, cpu_threads
        if not 0 < timeout_seconds <= 120 or not 1 <= cpu_threads <= 2:
            raise ValueError('Probe budgets must be bounded')

    def _run(self, arguments, *, deadline, max_output):
        command = [self.ffprobe, '-v', 'error', '-max_alloc', '67108864', '-threads', str(self.cpu_threads),
                   '-protocol_whitelist', 'file', '-err_detect', 'explode', *arguments]
        try:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, start_new_session=True)
        except OSError:
            raise IntakeError(503, 'service_unavailable', 'Video runtime is unavailable.') from None
        output, errors = bytearray(), bytearray()
        try:
            if os.name == 'nt':
                self._read_windows(process, output, errors, deadline, max_output)
                if process.returncode or errors:
                    raise _invalid()
                return json.loads(output)
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ, (output, max_output))
                selector.register(process.stderr, selectors.EVENT_READ, (errors, 65536))
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise _invalid('Video decode time budget exceeded.')
                    for key, _ in selector.select(min(remaining, .1)):
                        chunk = key.fileobj.read1(65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        target, limit = key.data
                        target.extend(chunk)
                        if len(target) > limit:
                            raise _invalid('Video metadata exceeds the decoding budget.')
            process.wait(timeout=max(.001, deadline - time.monotonic()))
            if process.returncode or errors:
                raise _invalid()
            return json.loads(output)
        except (json.JSONDecodeError, UnicodeDecodeError, subprocess.TimeoutExpired):
            raise _invalid() from None
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()
            process.stderr.close()

    @staticmethod
    def _read_windows(process, output, errors, deadline, max_output):
        """Windows selectors cannot select anonymous pipes; bound both readers."""
        overflow = threading.Event()
        def read(pipe, target, limit):
            while True:
                chunk = pipe.read1(65536)
                if not chunk:
                    return
                if len(target) + len(chunk) > limit:
                    overflow.set()
                    return
                target.extend(chunk)
        readers = [threading.Thread(target=read, args=args, daemon=True) for args in
                   [(process.stdout, output, max_output), (process.stderr, errors, 65536)]]
        for thread in readers:
            thread.start()
        try:
            while any(thread.is_alive() for thread in readers):
                if overflow.is_set():
                    raise _invalid('Video metadata exceeds the decoding budget.')
                if time.monotonic() >= deadline:
                    raise _invalid('Video decode time budget exceeded.')
                for thread in readers:
                    thread.join(.02)
            if overflow.is_set():
                raise _invalid('Video metadata exceeds the decoding budget.')
            process.wait(timeout=max(.001, deadline-time.monotonic()))
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            for thread in readers:
                thread.join(timeout=2)

    def validate(self, path: Path, *, size_bytes: int, deadline_monotonic: float) -> AcceptedUpload:
        path = Path(path).resolve(strict=True)
        if size_bytes > MAX_UPLOAD_BYTES or path.stat().st_size > MAX_UPLOAD_BYTES:
            raise IntakeError(413, 'upload_too_large', 'Upload exceeds the byte limit.')
        if size_bytes <= 0 or path.stat().st_size != size_bytes:
            raise _invalid('Upload size is invalid.')
        deadline = min(deadline_monotonic, time.monotonic() + self.timeout_seconds)
        metadata = self._run(['-select_streams', 'v:0', '-show_entries',
            'stream=codec_name,width,height,time_base,start_pts,duration,avg_frame_rate:stream_side_data=rotation:format=format_name,duration:format_tags=major_brand',
            '-of', 'json', str(path)], deadline=deadline, max_output=131072)
        try:
            streams = metadata.get('streams', [])
            format_info = metadata.get('format', {})
            if not streams or 'mov' not in format_info.get('format_name', '').split(','):
                raise _unsupported()
            brand = format_info.get('tags', {}).get('major_brand', '').strip().lower()
            if brand and not brand.startswith(('iso', 'mp4', 'qt', 'avc', 'm4v')):
                raise _unsupported()
            stream = streams[0]
            if stream.get('codec_name') not in ('h264', 'hevc', 'mpeg4', 'mjpeg', 'prores'):
                raise _unsupported()
            width, height = int(stream['width']), int(stream['height'])
            if min(width, height) <= 0 or max(width, height) > 1920 or min(width, height) > 1080:
                raise _unsupported()
            time_base = Fraction(stream['time_base'])
            if time_base <= 0:
                raise _invalid()
            declared_duration = float(stream.get('duration', 0))
            if not math.isfinite(declared_duration) or declared_duration > 180:
                raise _unsupported()
            average = stream.get('avg_frame_rate', '0/0')
            declared_fps = float(Fraction(average)) if average != '0/0' else 0
            if declared_fps > 60 + 1e-6:
                raise _unsupported()
            rotation = float(next((x['rotation'] for x in stream.get('side_data_list', []) if 'rotation' in x), 0))
            if not math.isfinite(rotation) or rotation % 90:
                raise _unsupported('Unsupported display rotation.')
            rotation = int(rotation) % 360
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
            if isinstance(error, IntakeError):
                raise
            raise _invalid('Video metadata is invalid.') from None
        decoded = self._run(['-select_streams', 'v:0', '-show_frames', '-show_entries',
            'frame=pts,duration,pkt_duration,width,height', '-of', 'json', str(path)],
            deadline=deadline, max_output=4 * 1024 * 1024)
        frames = decoded.get('frames', [])
        if not 0 < len(frames) <= 10801:
            raise _unsupported()
        try:
            points = [int(frame['pts']) for frame in frames]
            for frame in frames:
                if (int(frame['width']), int(frame['height'])) != (width, height):
                    raise _unsupported('Changing video dimensions are unsupported.')
            gaps = [float((b-a) * time_base) for a, b in zip(points, points[1:])]
            if any(gap < 1/60 - 1e-6 for gap in gaps):
                raise _unsupported('Decoded frame rate exceeds 60 fps or timestamps are invalid.')
            tail = int(frames[-1].get('duration', frames[-1].get('pkt_duration', 0)))
            duration = max(declared_duration, float((points[-1]-points[0]+max(tail, 0)) * time_base))
            if not 0 < duration <= 180 + 1e-6:
                raise _unsupported()
            fps = (len(points)-1)/sum(gaps) if gaps else declared_fps
            if not 0 < fps <= 60 + 1e-6:
                raise _unsupported()
            vfr = bool(gaps and max(gaps)-min(gaps) > max(float(time_base), 1e-6))
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
            if isinstance(error, IntakeError):
                raise
            raise _invalid('Video frame timestamps are invalid.') from None
        with path.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        return AcceptedUpload(path, digest, size_bytes,
                              VideoInfo(duration, width, height, fps, rotation, points[0],
                                        time_base.numerator, time_base.denominator, vfr))
