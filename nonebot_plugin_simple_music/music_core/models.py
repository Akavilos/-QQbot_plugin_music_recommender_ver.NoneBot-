"""将音源差异收束为明确的歌曲记录与消息载荷。"""
from dataclasses import dataclass

@dataclass(frozen=True)
class Song:
    source: str
    id: str
    title: str
    artist: str
    url: str
    album: str = ''
    seconds: int = 0
    cover: str = ''
    audio: str = ''
    card_id: str = ''

    @property
    def duration(self):
        return f'{self.seconds//60}:{self.seconds%60:02d}' if self.seconds else ''

@dataclass(frozen=True)
class Card:
    kind: str
    data: dict
