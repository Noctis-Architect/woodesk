"""Run blocking functions (HTTP calls) off the UI thread and deliver results on it."""
from __future__ import annotations

import logging
import traceback
from functools import partial

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

log = logging.getLogger("woodesk")


class _Dispatcher(QObject):
    call = Signal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(self._run)

    @Slot(object)
    def _run(self, fn):
        try:
            fn()
        except RuntimeError:
            pass  # widget was deleted before the result arrived
        except Exception:
            log.error("callback failed:\n%s", traceback.format_exc())


_dispatcher: _Dispatcher | None = None


class _Task(QRunnable):
    def __init__(self, fn, args, kwargs, ok, err):
        super().__init__()
        self.fn, self.args, self.kwargs, self.ok, self.err = fn, args, kwargs, ok, err

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:  # noqa: BLE001
            if self.err:
                _dispatcher.call.emit(partial(self.err, e))
            else:
                log.error("worker failed: %s", e)
            return
        if self.ok:
            _dispatcher.call.emit(partial(self.ok, result))


def run_async(fn, *args, ok=None, err=None, **kwargs) -> None:
    """Call from the UI thread. `ok(result)` / `err(exception)` run on the UI thread."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = _Dispatcher()
    QThreadPool.globalInstance().start(_Task(fn, args, kwargs, ok, err))
