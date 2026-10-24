from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class JobCancelled(RuntimeError):
    pass


class Job(QObject):
    progress = Signal(int, str)
    finished = Signal(object)
    failed = Signal(object)
    cancelled_signal = Signal()

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn
        self._cancelled = False
        self._started = False

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True

    def report(self, pct: int, key: str) -> None:
        self.progress.emit(max(0, min(100, int(pct))), str(key))

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        QThreadPool.globalInstance().start(_JobRunnable(self))

    def _execute(self) -> None:
        try:
            result = self._fn(self)
        except JobCancelled:
            self.cancelled_signal.emit()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(exc)
        else:
            self.finished.emit(result)


class _JobRunnable(QRunnable):
    def __init__(self, job: Job):
        super().__init__()
        self.job = job

    def run(self) -> None:
        self.job._execute()


def run_job(fn, parent=None) -> Job:
    job = Job(fn, parent)
    job.start()
    return job
