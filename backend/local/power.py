"""Keep the Windows host available while the local service worker is running."""
import ctypes
import logging
import os


ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
logger = logging.getLogger(__name__)


def _execution_state_setter():
    if os.name != 'nt':
        return None
    setter = ctypes.WinDLL('kernel32', use_last_error=True).SetThreadExecutionState
    setter.argtypes = [ctypes.c_uint32]
    setter.restype = ctypes.c_uint32
    return setter


class IdleSleepInhibitor:
    """Enter and exit on the same worker thread; leave the display timer alone."""

    def __init__(self):
        self.active = False
        self._setter = None
        self._previous = 0

    def __enter__(self):
        try:
            self._setter = _execution_state_setter()
            if self._setter is not None:
                self._previous = self._setter(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
                self.active = bool(self._previous)
                if not self.active:
                    logger.warning('Windows idle sleep prevention is unavailable')
        except OSError:
            logger.warning('Windows idle sleep prevention is unavailable', exc_info=True)
        return self

    def __exit__(self, *exc):
        try:
            if self.active and not self._setter(self._previous | ES_CONTINUOUS):
                logger.warning('Could not restore the worker execution state')
        finally:
            self.active = False
