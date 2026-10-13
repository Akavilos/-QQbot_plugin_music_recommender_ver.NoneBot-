"""推荐操作只记录确认成功的卡片；未成功的歌曲仍提供真实播放页面。"""
from .config import MusicError
from .models import Card

class MusicService:
    def __init__(self,settings,client,logger):
        self.settings,self.client,self.logger=settings,client,logger

    def format_songs(self,songs):
        lines=[]
        for i,song in enumerate(songs,1):
            line=f'{i}. {song.title} — {song.artist}'
            details=[]
            if self.settings.show_album and song.album:details.append(song.album)
            if self.settings.show_duration and song.duration:details.append(song.duration)
            if details:line+='（'+' · '.join(details)+'）'
            if self.settings.show_link and song.url:line+='\n'+song.url
            lines.append(line)
        return '\n'.join(lines)

    async def make_card(self,song):
        mode=self.settings.send_mode
        if mode=='card':
            if song.source=='netease':return Card('music',{'type':'163','id':song.id})
            if not song.card_id.isdigit():raise MusicError('QQ音乐没有返回有效卡片编号，改用播放页面')
            return Card('music',{'type':'qq','id':song.card_id})
        if mode=='card_api':return Card('json',{'data':await self.client.signed_card(song)})
        if mode=='custom':
            cover,audio=await self.client.extras(song)
            if not audio:raise MusicError('没有可用的公开音源，改用歌曲播放页面')
            return Card('music',{'type':'custom','url':song.url,'audio':audio,'title':song.title,
                                 'content':song.artist,'image':cover})
        raise MusicError('当前发送方式不发送音乐卡片')

    async def recommend(self,keyword,limit,send):
        if not self.settings.enable_tool:return '音乐搜索功能已关闭。'
        if not isinstance(keyword,str) or not keyword.strip():return '请输入歌名、歌手或关键词。'
        keyword=keyword.strip()
        if len(keyword)>200:return '搜索关键词过长，请缩短到200字以内。'
        try:
            songs=await self.client.search(keyword,self.settings.limit(limit))
        except MusicError as error:
            self.logger.warning(f'[音乐搜索] {error}')
            return f'搜索未完成：{error}。'
        except (ValueError,TypeError,KeyError):
            self.logger.warning('[音乐搜索] 音乐平台返回的歌曲数据格式发生变化')
            return '音乐平台返回的歌曲数据格式发生变化，本次搜索未完成。'
        if not songs:return '没有找到匹配的歌曲。'
        listing=self.format_songs(songs)
        if self.settings.send_mode=='link':return '我查到这些歌曲：\n'+listing
        sent=[];failed=[]
        for song in songs[:self.settings.card_count]:
            try:
                card=await self.make_card(song)
            except MusicError as error:
                failed.append(song.title)
                self.logger.warning(f'[音乐卡片] {error}')
                continue
            except (ValueError,TypeError,KeyError):
                failed.append(song.title)
                self.logger.warning('[音乐卡片] 音乐服务返回的卡片数据格式发生变化')
                continue
            try:
                receipt=await send(card)
                if receipt is False:raise MusicError('发送接口未确认成功')
            except Exception:
                failed.append(song.title)
                self.logger.warning('[音乐卡片] 发送未确认成功；歌曲信息仍可查看')
                continue
            sent.append(song.title)
        status=f'我已确认发送 {len(sent)} 张音乐卡片：'+ '、'.join(sent)+'。' if sent else '音乐卡片未发送成功，以下提供歌曲信息。'
        if failed and sent:status+='未成功发送：'+'、'.join(failed)+'。'
        return status+'\n'+listing
