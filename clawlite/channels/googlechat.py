from __future__ import annotations

from clawlite.channels.base import PassiveChannel


class GoogleChatChannel(PassiveChannel):
    def __init__(self, *, config: dict, on_message=None) -> None:
        super().__init__(name="googlechat", config=config, on_message=on_message)
