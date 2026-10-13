"""读取分组或旧平铺设置；框架入口负责保存配置。"""
from dataclasses import dataclass
from urllib.parse import urlsplit

class MusicError(ValueError):
    """可直接展示的音乐服务或参数错误，不携带请求密钥。"""

GROUPS = {
    'basic': ('enable_tool','music_source','send_mode','default_limit','card_count'),
    'display': ('show_album','show_duration','show_link'),
    'search': ('search_timeout','max_results_hard_limit','cache_seconds'),
    'signing': ('sign_api_url','sign_api_key','sign_api_format'),
}

@dataclass(frozen=True)
class Settings:
    enable_tool: bool = True
    music_source: str = 'netease'
    send_mode: str = 'link'
    default_limit: int = 3
    card_count: int = 1
    show_album: bool = True
    show_duration: bool = True
    show_link: bool = True
    search_timeout: int = 10
    max_results_hard_limit: int = 8
    cache_seconds: int = 120
    sign_api_url: str = ''
    sign_api_key: str = ''
    sign_api_format: str = ''

    @classmethod
    def from_mapping(cls, config):
        values={}
        for group,names in GROUPS.items():
            for name in names:
                if name in config.get(group,{}):values[name]=config[group][name]
                elif name in config:values[name]=config[name]
        if values.get('send_mode')=='ark':values['send_mode']='custom'
        settings=cls(**values)
        if settings.music_source not in ('netease','qqmusic'):raise MusicError('音乐平台应选网易云或QQ音乐')
        if settings.send_mode not in ('link','card','card_api','custom'):raise MusicError('歌曲发送方式不受支持')
        ranges={'default_limit':(1,20),'card_count':(1,3),'search_timeout':(3,30),
                'max_results_hard_limit':(1,20),'cache_seconds':(0,600)}
        for key,(minimum,maximum) in ranges.items():
            value=getattr(settings,key)
            if type(value) is not int or not minimum<=value<=maximum:raise MusicError(f'{key} 应为 {minimum} 到 {maximum} 的整数')
        for key in ('enable_tool','show_album','show_duration','show_link'):
            if type(getattr(settings,key)) is not bool:raise MusicError(f'{key} 应为开关值')
        for key in ('sign_api_url','sign_api_key','sign_api_format'):
            if not isinstance(getattr(settings,key),str):raise MusicError(f'{key} 应为文字')
        if settings.sign_api_url:
            url=urlsplit(settings.sign_api_url)
            if url.scheme!='https' or not url.hostname or url.username or url.password:
                raise MusicError('独立签名服务使用不含账号密码的HTTPS地址')
        return settings

    def limit(self, value=None):
        if value in (None,''):value=self.default_limit
        try:
            number=int(value)
        except (ValueError,TypeError):raise MusicError('歌曲数量应为整数') from None
        if isinstance(value,bool) or (isinstance(value,float) and value!=number):raise MusicError('歌曲数量应为整数')
        return max(1,min(number,self.max_results_hard_limit))

    def grouped(self):
        return {group:{key:getattr(self,key) for key in names} for group,names in GROUPS.items()}
