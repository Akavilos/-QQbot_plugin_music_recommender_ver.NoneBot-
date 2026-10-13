"""通用NoneBot搜歌入口；文字结果跨适配器，音乐卡片使用OneBot V11。"""
from nonebot import get_driver,get_plugin_config,on_command
from nonebot.adapters import Bot,Event,Message
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from nonebot import logger
from nonebot.compat import model_dump
from pydantic import BaseModel
from .music_core import Settings,MusicClient,MusicService,MusicError

class Config(BaseModel):
    simple_music_enable_tool: bool = True
    simple_music_music_source: str = 'netease'
    simple_music_send_mode: str = 'link'
    simple_music_default_limit: int = 3
    simple_music_card_count: int = 1
    simple_music_show_album: bool = True
    simple_music_show_duration: bool = True
    simple_music_show_link: bool = True
    simple_music_search_timeout: int = 10
    simple_music_max_results_hard_limit: int = 8
    simple_music_cache_seconds: int = 120
    simple_music_sign_api_url: str = ''
    simple_music_sign_api_key: str = ''
    simple_music_sign_api_format: str = ''

__plugin_meta__=PluginMetadata(name='简单音乐推荐插件',description='网易云与QQ音乐搜索、卡片分享和播放链接',
    usage='/搜歌 歌名、歌手或关键词（也可使用 /音乐）',type='application',config=Config,
    homepage='https://github.com/Akavilos/-QQbot_plugin_music_recommender_ver.NoneBot-')

config=get_plugin_config(Config)
settings=Settings.from_mapping({key.removeprefix('simple_music_'):value for key,value in model_dump(config).items()})
client=MusicClient(settings)
service=MusicService(settings,client,logger)
driver=get_driver()
driver.on_startup(client.open)
driver.on_shutdown(client.close)
delivery_handler=None

def get_music_service():
    """其他AI插件可将自己的发送函数传给recommend，共用真实音乐搜索。"""
    return service

def configure_delivery(handler):
    """宿主可明确提供统一发送接口；没有提供时沿用NoneBot发送。"""
    global delivery_handler
    delivery_handler=handler

async def send_card(bot:Bot,event:Event,card):
    if delivery_handler is not None:return await delivery_handler(bot,event,card.kind,card.data)
    try:
        from nonebot.adapters.onebot.v11 import Bot as OneBot,MessageSegment
    except ImportError:raise MusicError('音乐卡片需要OneBot V11适配器，可使用播放链接') from None
    if not isinstance(bot,OneBot):raise MusicError('当前适配器不支持QQ音乐卡片，可使用播放链接')
    return await bot.send(event,MessageSegment(card.kind,card.data))

search_command=on_command('搜歌',aliases={'音乐'},priority=10,block=True)

@search_command.handle()
async def search(bot:Bot,event:Event,argument:Message=CommandArg()):
    keyword=argument.extract_plain_text().strip()
    async def send(card):return await send_card(bot,event,card)
    text=await service.recommend(keyword,None,send) if keyword else '用法：/搜歌 歌名、歌手或关键词；也可使用 /音乐。'
    if delivery_handler is not None:await delivery_handler(bot,event,'text',{'text':text})
    else:await bot.send(event,text)
    await search_command.finish()
