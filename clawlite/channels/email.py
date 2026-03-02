from __future__ import annotations

from clawlite.channels.base import PassiveChannel


class EmailChannel(PassiveChannel):
    def __init__(self, *, config: dict, on_message=None) -> None:
        super().__init__(name="email", config=config, on_message=on_message)
