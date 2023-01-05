import atexit
import ctypes
import logging
import platform
import shutil
import sys
import time
from logging import FileHandler, Formatter, Logger, getLogger
from pathlib import Path
from signal import SIGINT, SIGTERM, signal
from subprocess import DEVNULL, PIPE, Popen
from typing import List, Optional

from ape.api.providers.provider import ProviderAPI
from ape.exceptions import ProviderError, RPCTimeoutError, SubprocessError, SubprocessTimeoutError
from ape.logging import LogLevel, logger
from ape.utils import JoinableQueue, abstractmethod, cached_property, spawn


class SubprocessProvider(ProviderAPI):
    """
    A provider that manages a process, such as for ``ganache``.
    """

    PROCESS_WAIT_TIMEOUT = 15
    process: Optional[Popen] = None
    is_stopping: bool = False

    stdout_queue: Optional[JoinableQueue] = None
    stderr_queue: Optional[JoinableQueue] = None

    @property
    @abstractmethod
    def process_name(self) -> str:
        """The name of the process, such as ``Hardhat node``."""

    @abstractmethod
    def build_command(self) -> List[str]:
        """
        Get the command as a list of ``str``.
        Subclasses should override and add command arguments if needed.

        Returns:
            List[str]: The command to pass to ``subprocess.Popen``.
        """

    @property
    def base_logs_path(self) -> Path:
        return self.config_manager.DATA_FOLDER / self.name / "subprocess_output"

    @property
    def stdout_logs_path(self) -> Path:
        return self.base_logs_path / "stdout.log"

    @property
    def stderr_logs_path(self) -> Path:
        return self.base_logs_path / "stderr.log"

    @cached_property
    def _stdout_logger(self) -> Logger:
        return self._get_process_output_logger("stdout", self.stdout_logs_path)

    @cached_property
    def _stderr_logger(self) -> Logger:
        return self._get_process_output_logger("stderr", self.stderr_logs_path)

    def _get_process_output_logger(self, name: str, path: Path):
        logger = getLogger(f"{self.name}_{name}_subprocessProviderLogger")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file():
            path.unlink()

        path.touch()
        handler = FileHandler(str(path))
        handler.setFormatter(Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        return logger

    def connect(self):
        """
        Start the process and connect to it.
        Subclasses handle the connection-related tasks.
        """

        if self.is_connected:
            raise ProviderError("Cannot connect twice. Call disconnect before connecting again.")

        # Register atexit handler to make sure disconnect is called for normal object lifecycle.
        atexit.register(self.disconnect)

        # Register handlers to ensure atexit handlers are called when Python dies.
        def _signal_handler(signum, frame):
            atexit._run_exitfuncs()
            sys.exit(143 if signum == SIGTERM else 130)

        signal(SIGINT, _signal_handler)
        signal(SIGTERM, _signal_handler)

    def disconnect(self):
        """Stop the process if it exists.
        Subclasses override this method to do provider-specific disconnection tasks.
        """

        self.cached_chain_id = None
        if self.process:
            self.stop()

    def start(self, timeout: int = 20):
        """Start the process and wait for its RPC to be ready."""

        if self.is_connected:
            logger.info(f"Connecting to existing '{self.process_name}' process.")
            self.process = None  # Not managing the process.
        else:
            logger.info(f"Starting '{self.process_name}' process.")
            pre_exec_fn = _linux_set_death_signal if platform.uname().system == "Linux" else None
            self.stderr_queue = JoinableQueue()
            self.stdout_queue = JoinableQueue()
            out_file = PIPE if logger.level <= LogLevel.DEBUG else DEVNULL
            self.process = Popen(
                self.build_command(), preexec_fn=pre_exec_fn, stdout=out_file, stderr=out_file
            )
            spawn(self.produce_stdout_queue)
            spawn(self.produce_stderr_queue)
            spawn(self.consume_stdout_queue)
            spawn(self.consume_stderr_queue)

            with RPCTimeoutError(self, seconds=timeout) as _timeout:
                while True:
                    if self.is_connected:
                        break

                    time.sleep(0.1)
                    _timeout.check()

    def produce_stdout_queue(self):
        process = self.process
        if self.stdout_queue is None or process is None:
            return

        stdout = process.stdout
        if stdout is None:
            return

        for line in iter(stdout.readline, b""):
            self.stdout_queue.put(line)
            time.sleep(0)

    def produce_stderr_queue(self):
        process = self.process
        if self.stderr_queue is None or process is None:
            return

        stderr = process.stderr
        if stderr is None:
            return

        for line in iter(stderr.readline, b""):
            self.stderr_queue.put(line)
            time.sleep(0)

    def consume_stdout_queue(self):
        if self.stdout_queue is None:
            return

        for line in self.stdout_queue:
            output = line.decode("utf8").strip()
            logger.debug(output)
            self._stdout_logger.debug(output)

            if self.stdout_queue is not None:
                self.stdout_queue.task_done()

            time.sleep(0)

    def consume_stderr_queue(self):
        if self.stderr_queue is None:
            return

        for line in self.stderr_queue:
            logger.debug(line.decode("utf8").strip())
            self._stdout_logger.debug(line)

            if self.stderr_queue is not None:
                self.stderr_queue.task_done()

            time.sleep(0)

    def stop(self):
        """Kill the process."""

        if not self.process or self.is_stopping:
            return

        self.is_stopping = True
        logger.info(f"Stopping '{self.process_name}' process.")
        self._kill_process()
        self.is_stopping = False
        self.process = None

    def _wait_for_popen(self, timeout: int = 30):
        if not self.process:
            # Mostly just to make mypy happy.
            raise SubprocessError("Unable to wait for process. It is not set yet.")

        try:
            with SubprocessTimeoutError(self, seconds=timeout) as _timeout:
                while self.process.poll() is None:
                    time.sleep(0.1)
                    _timeout.check()

        except SubprocessTimeoutError:
            pass

    def _kill_process(self):
        if platform.uname().system == "Windows":
            self._windows_taskkill()
            return

        warn_prefix = f"Trying to close '{self.process_name}' process."

        def _try_close(warn_message):
            try:
                if self.process:
                    self.process.send_signal(SIGINT)

                self._wait_for_popen(self.PROCESS_WAIT_TIMEOUT)
            except KeyboardInterrupt:
                logger.warning(warn_message)

        try:
            if self.process is not None and self.process.poll() is None:
                _try_close(f"{warn_prefix}. Press Ctrl+C 1 more times to force quit")

            if self.process is not None and self.process.poll() is None:
                self.process.kill()
                self._wait_for_popen(2)

        except KeyboardInterrupt:
            if self.process is not None:
                self.process.kill()

        self.process = None

    def _windows_taskkill(self) -> None:
        """
        Kills the given process and all child processes using taskkill.exe. Used
        for subprocesses started up on Windows which run in a cmd.exe wrapper that
        doesn't propagate signals by default (leaving orphaned processes).
        """
        process = self.process
        if not process:
            return

        taskkill_bin = shutil.which("taskkill")
        if not taskkill_bin:
            raise SubprocessError("Could not find taskkill.exe executable.")

        proc = Popen(
            [
                taskkill_bin,
                "/F",  # forcefully terminate
                "/T",  # terminate child processes
                "/PID",
                str(process.pid),
            ]
        )
        proc.wait(timeout=self.PROCESS_WAIT_TIMEOUT)


def _linux_set_death_signal():
    """
    Automatically sends SIGTERM to child subprocesses when parent process
    dies (only usable on Linux).
    """
    # from: https://stackoverflow.com/a/43152455/75956
    # the first argument, 1, is the flag for PR_SET_PDEATHSIG
    # the second argument is what signal to send to child subprocesses
    libc = ctypes.CDLL("libc.so.6")
    return libc.prctl(1, SIGTERM)
