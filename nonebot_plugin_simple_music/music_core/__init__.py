"""与运行框架无关的音乐搜索和推荐服务。"""
from .config import Settings, MusicError
from .client import MusicClient
from .service import MusicService

__all__ = ['Settings', 'MusicError', 'MusicClient', 'MusicService']
