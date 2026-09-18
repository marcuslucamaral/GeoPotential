"""WorkerSupervisor — owns the scientific worker child process.

Section 11: the worker starts on request from the application layer, performs a
handshake, announces its capabilities, receives jobs, reports progress, emits
artefacts, accepts cancellation, records failures, and shuts down in a
controlled way. It never runs inside the GUI process.

Section 12.1: `QProcess` for start, observe, restart and terminate, with stdout
and stderr kept separate. stdout is the protocol; stderr is the worker log.

The GUI thread is never blocked. Everything here is signal-driven.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from ..ipc import protocol as P
from ..utils.paths import worker_package_root
from ..utils.qtcore import (
    QObject,
    QProcess,
    QProcessEnvironment,
    QTimer,
    Signal,
)


class WorkerSupervisor(QObject):
    """One worker child, started once, restarted only on request or on crash.

    Signals carry decoded messages. Nothing that reads them needs to know the
    result came from Python, from a cache, or from anywhere else.
    """

    helloReceived = Signal(dict)
    progressReceived = Signal(dict)
    artifactReceived = Signal(dict)
    jobSucceeded = Signal(dict)
    jobFailed = Signal(dict)
    logLine = Signal(str)
    stateChanged = Signal(str)
    protocolMismatch = Signal(str, str)  # ours, theirs

    STOPPED = "stopped"
    STARTING = "starting"
    READY = "ready"
    CRASHED = "crashed"
    INCOMPATIBLE = "incompatible"

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: QProcess | None = None
        self._buffer = ""
        self._state = self.STOPPED
        self._capabilities: list[str] = []
        self._planned: dict[str, str] = {}
        self._worker_version = ""
        self._starts = 0
        # True only while `stop()` is asking. An exit we asked for is not
        # a crash, and classifying it as one would make every clean
        # shutdown offer a pointless restart.
        self._stopping = False

    # ---- state ----------------------------------------------------------

    @property
    def state(self) -> str:
        return self._state

    @property
    def capabilities(self) -> list[str]:
        return list(self._capabilities)

    @property
    def planned(self) -> dict[str, str]:
        return dict(self._planned)

    @property
    def worker_version(self) -> str:
        return self._worker_version

    @property
    def start_count(self) -> int:
        """How many times a worker child has been spawned in this session.

        The M1 gate asserts this is 1 after a full vertical slice: a worker
        started twice means the supervisor is not the single owner.
        """
        return self._starts

    def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.stateChanged.emit(state)

    # ---- lifecycle ------------------------------------------------------

    def start(self, python: str | None = None) -> None:
        """Spawn the worker child. A second call while it is alive is refused.

        python  interpreter to run the worker with; the current one by default
        """
        if self._process is not None and self._process.state() != QProcess.NotRunning:
            raise RuntimeError(
                "a worker is already running; call restart() to replace it"
            )
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.SeparateChannels)
        proc.readyReadStandardOutput.connect(self._read_stdout)
        proc.readyReadStandardError.connect(self._read_stderr)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)

        # The parent's environment, then our two additions. A child given only
        # the two would lose PATH and LD_LIBRARY_PATH, which a frozen build
        # depends on to find the libraries beside it.
        env = QProcessEnvironment.systemEnvironment()
        worker_root = str(worker_package_root())
        existing = os.environ.get("PYTHONPATH", "")
        env.insert("PYTHONPATH", f"{worker_root}{os.pathsep}{existing}" if existing else worker_root)
        env.insert("PYTHONUNBUFFERED", "1")
        proc.setProcessEnvironment(env)

        self._process = proc
        self._buffer = ""
        self._starts += 1
        self._set_state(self.STARTING)
        proc.start(*self._command(python))

    @staticmethod
    def _command(python: str | None) -> tuple[str, list[str]]:
        """What to run, and with what arguments.

        In a checkout: an interpreter, and `-m geopotential_worker`.

        Frozen: **there is no interpreter to give `-m` to.** `sys.executable`
        is the bundled binary, so `-m geopotential_worker` would start a second
        copy of the application. The binary knows how to be either process and
        the switch says which — `tools/frozen_entry.py`. The two are still two
        processes with two PIDs; what they share is one file on disk.
        """
        if python:
            return python, ["-m", "geopotential_worker"]
        if getattr(sys, "frozen", False):
            return sys.executable, ["--worker"]
        return sys.executable, ["-m", "geopotential_worker"]

    def restart(self, python: str | None = None) -> None:
        """Replace the worker. The project survives; the run in flight does not."""
        self.stop(force=True)
        self.start(python)

    def stop(self, *, force: bool = False, deadline_ms: int = 5000) -> None:
        """Ask the worker to finish, then make sure it did.

        Section 12.3 `shutdown`: the worker completes a transaction in flight or
        records recovery before exiting. `force` skips the ask.

        Gate M2, "fechar a janela encerra os filhos". A supervisor that only
        sends `shutdown` and returns leaves an orphan whenever the worker is
        wedged — and a wedged worker is exactly the case the requirement is
        about. So the deadline is real: ask, wait, `terminate`, wait, `kill`,
        and only then report stopped. `_stopping` suppresses the crash
        classification, because an exit we asked for is not a crash.
        """
        proc = self._process
        if proc is None or proc.state() == QProcess.NotRunning:
            self._set_state(self.STOPPED)
            return

        self._stopping = True
        try:
            if not force:
                try:
                    self.send(P.message(P.SHUTDOWN, deadline=f"{deadline_ms}ms"))
                    proc.closeWriteChannel()
                except RuntimeError:
                    pass  # the pipe is already gone; fall through to the kill
                if proc.waitForFinished(deadline_ms):
                    self._set_state(self.STOPPED)
                    return

            # SIGTERM first: it lets the worker's own handlers run. Then
            # SIGKILL, which nothing can ignore.
            proc.terminate()
            if not proc.waitForFinished(2000):
                proc.kill()
                proc.waitForFinished(2000)
            self._set_state(self.STOPPED)
        finally:
            self._stopping = False

    def kill_now(self) -> int:
        """SIGKILL the worker without asking. Returns the pid that was killed.

        This exists for the M2 crash tests, which have to produce the failure
        the recovery pass is supposed to survive. Naming it plainly is better
        than a test reaching into `_process`.
        """
        proc = self._process
        if proc is None or proc.state() == QProcess.NotRunning:
            return 0
        pid = int(proc.processId())
        proc.kill()
        proc.waitForFinished(2000)
        return pid

    # ---- sending --------------------------------------------------------

    def send(self, msg: dict) -> None:
        """Write one message to the worker's stdin.

        raises  RuntimeError if no worker is running — a job submitted into a
                dead pipe must fail loudly, not vanish
        """
        proc = self._process
        if proc is None or proc.state() == QProcess.NotRunning:
            raise RuntimeError("no worker is running; start it before submitting")
        try:
            line = P.encode(msg)
        except TypeError as exc:
            # A value that cannot be JSON-encoded reached the wire. Caught here
            # rather than inside json, because the useful information — which
            # message, which job — exists at this level and not at that one.
            raise TypeError(
                f"cannot send {msg.get('type')} for job "
                f"{msg.get('job_id', '?')}: {exc}. A value from QML probably "
                f"arrived as a QJSValue; coerce it with utils.fromqml.to_python "
                f"at the slot boundary."
            ) from exc
        proc.write((line + "\n").encode("utf-8"))

    def submit(
        self, job_id: str, operator: str, params: dict, inputs: list[str], output_dir: Path
    ) -> None:
        self.send(
            P.message(
                P.SUBMIT_JOB,
                job_id=job_id,
                operator=operator,
                params=params,
                inputs=[str(p) for p in inputs],
                output_dir=str(output_dir),
            )
        )

    def cancel(self, job_id: str, reason: str = "user requested") -> None:
        self.send(P.message(P.CANCEL_JOB, job_id=job_id, reason=reason))

    # ---- receiving ------------------------------------------------------

    def _read_stdout(self) -> None:
        proc = self._process
        if proc is None:
            return
        self._buffer += bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                self._dispatch(line)

    def _read_stderr(self) -> None:
        proc = self._process
        if proc is None:
            return
        text = bytes(proc.readAllStandardError()).decode("utf-8", "replace")
        for line in text.splitlines():
            if line.strip():
                self.logLine.emit(line)

    def _dispatch(self, line: str) -> None:
        try:
            msg = P.decode(line)
        except P.ProtocolError as exc:
            self.logLine.emit(f'{{"level":"error","msg":"unreadable from worker: {exc}"}}')
            return

        kind = msg["type"]
        if kind == P.HELLO:
            theirs = msg["protocol"]
            self._capabilities = list(msg.get("capabilities", []))
            self._planned = dict(msg.get("planned", {}))
            self._worker_version = str(msg.get("worker", ""))
            if not P.compatible(theirs):
                # Section 12.3: incompatibility blocks execution. It never
                # degrades into a partial mode where some operators work.
                self._set_state(self.INCOMPATIBLE)
                self.protocolMismatch.emit(P.PROTOCOL_VERSION, theirs)
                self.stop(force=True)
                return
            self._set_state(self.READY)
            self.helloReceived.emit(msg)
        elif kind == P.JOB_PROGRESS:
            self.progressReceived.emit(msg)
        elif kind == P.JOB_ARTIFACT:
            self.artifactReceived.emit(msg)
        elif kind == P.JOB_SUCCEEDED:
            self.jobSucceeded.emit(msg)
        elif kind == P.JOB_FAILED:
            self.jobFailed.emit(msg)
        elif kind == P.GOODBYE:
            self._set_state(self.STOPPED)

    def _on_finished(self, code: int, status) -> None:  # noqa: ANN001 - Qt enum
        if self._stopping:
            self._set_state(self.STOPPED)
            return
        if self._state not in (self.STOPPED, self.INCOMPATIBLE):
            self._set_state(self.CRASHED)
            self.logLine.emit(
                f'{{"level":"error","msg":"worker exited unexpectedly","code":{code}}}'
            )

    def _on_error(self, error) -> None:  # noqa: ANN001 - Qt enum
        if error == QProcess.FailedToStart:
            self._set_state(self.CRASHED)
            self.logLine.emit(
                '{"level":"error","msg":"worker failed to start; check the interpreter"}'
            )

    def wait_for_ready(self, timeout_ms: int = 15000) -> bool:
        """Block until the handshake lands. For headless gates only.

        The interactive application never calls this: it reacts to
        `helloReceived`. A gate needs a synchronous point, and saying so here
        is better than a sleep in the test.
        """
        proc = self._process
        if proc is None:
            return False
        deadline = QTimer()
        deadline.setSingleShot(True)
        elapsed = 0
        step = 50
        while elapsed < timeout_ms:
            if self._state in (self.READY, self.INCOMPATIBLE, self.CRASHED):
                return self._state == self.READY
            proc.waitForReadyRead(step)
            self._read_stdout()
            self._read_stderr()
            elapsed += step
        return False

    def pump(self, ms: int = 50) -> None:
        """Drain whatever the worker has written. For headless gates only."""
        proc = self._process
        if proc is None:
            return
        proc.waitForReadyRead(ms)
        self._read_stdout()
        self._read_stderr()
