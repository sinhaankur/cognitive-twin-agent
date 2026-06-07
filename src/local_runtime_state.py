from __future__ import annotations

from dataclasses import dataclass
import threading


@dataclass
class RuntimeState:
    stop_requested: bool = False
    quick_voice_trigger_requested: bool = False
    completed_iterations: int = 0


class RuntimeStateHandle:
    def __init__(self) -> None:
        self.state = RuntimeState()
        self._lock = threading.Lock()

    def snapshot(self) -> RuntimeState:
        with self._lock:
            return RuntimeState(
                stop_requested=self.state.stop_requested,
                quick_voice_trigger_requested=self.state.quick_voice_trigger_requested,
                completed_iterations=self.state.completed_iterations,
            )

    def request_stop(self) -> None:
        with self._lock:
            self.state.stop_requested = True

    def request_quick_voice_trigger(self) -> None:
        with self._lock:
            self.state.quick_voice_trigger_requested = True

    def consume_quick_voice_trigger(self) -> bool:
        with self._lock:
            if not self.state.quick_voice_trigger_requested:
                return False
            self.state.quick_voice_trigger_requested = False
            return True

    def increment_iterations(self) -> None:
        with self._lock:
            self.state.completed_iterations += 1

    def should_run(self) -> bool:
        with self._lock:
            return not self.state.stop_requested
