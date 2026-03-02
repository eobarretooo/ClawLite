from __future__ import annotations

from clawlite.channels.base import PassiveChannel


class MatrixChannel(PassiveChannel):
    def __init__(self, *, config: dict, on_message=None) -> None:
        super().__init__(name="matrix", config=config, on_message=on_message)
