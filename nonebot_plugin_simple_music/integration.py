"""可选角色工具桥接，仅通过宿主明确提供的注册与发送接口协作。"""
from . import get_music_service,configure_delivery

class SearchMusic:
    name='search_music'
    description=('我可以搜索歌曲并向当前会话发送音乐卡片；QQ客户端可显示封面与播放入口。'
                 '我需要发卡片时选择delivery=card，只查歌曲链接时选择delivery=link。'
                 '我按工具实际返回的发送结果判断卡片是否送达。')
    active=True
    parameters={'type':'object','properties':{
        'keyword':{'type':'string','description':'我用于搜歌的歌名、歌手或关键词'},
        'limit':{'type':'integer','description':'我需要的候选数量；省略时沿用默认值'},
        'delivery':{'type':'string','enum':['configured','card','link'],'description':'我需要发音乐卡片时用card；只查询链接时用link；省略时沿用设置'}},'required':['keyword']}

    def __init__(self,service,send):self.service,self.send=service,send

    async def call(self,wrapper,keyword,limit=None,delivery='configured'):
        return await self.service.recommend(keyword,limit,lambda card:self.send(wrapper.context.event,card),delivery=delivery)

def setup(api):
    # NoneBot管理生命周期；协作入口只注册AI工具，不重复注册指令或连接。
    from role_system.ports import MessageChain,NativeSegment,Plain
    service=get_music_service()
    async def send(event,card):
        return await event.send(MessageChain([NativeSegment(card.kind,card.data)]))
    if service.settings.enable_tool:api.tool(SearchMusic(service,send))
    async def deliver(bot,event,kind,data):
        group=getattr(event,'group_id',None)
        session=f"qq-{bot.self_id}:{'GroupMessage' if group is not None else 'FriendMessage'}:{group if group is not None else event.get_user_id()}"
        component=Plain(data['text']) if kind=='text' else NativeSegment(kind,data)
        return await api.send(session,MessageChain([component]))
    configure_delivery(deliver)
