"""复用异步连接和实例内短期缓存，音乐服务错误与无结果分开返回。"""
import asyncio,json,time
from collections import OrderedDict
from urllib.parse import urlsplit
import aiohttp
from .config import MusicError
from .models import Song

NETEASE_SEARCH='https://music.163.com/api/search/get/web'
QQ_SEARCH='https://u.y.qq.com/cgi-bin/musicu.fcg'
HEADERS={'User-Agent':'Mozilla/5.0','Accept':'application/json'}

def web_url(value):
    if not isinstance(value,str):return ''
    parsed=urlsplit(value)
    return value if parsed.scheme in ('http','https') and parsed.hostname and not parsed.username and not parsed.password else ''

class MusicClient:
    def __init__(self,settings):
        self.settings=settings
        self.session=None
        self.cache=OrderedDict()
        self.lock=asyncio.Lock()

    async def open(self):
        if self.session is None or self.session.closed:
            self.session=aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.settings.search_timeout),
                headers=HEADERS,connector=aiohttp.TCPConnector(limit=8))

    async def close(self):
        if self.session is not None:await self.session.close()
        self.cache.clear()

    async def request(self,method,url,*,label,params=None,headers=None,body=None):
        await self.open()
        try:
            async with self.session.request(method,url,params=params,headers=headers,json=body,allow_redirects=False) as response:
                if response.status!=200:raise MusicError(f'{label}返回 HTTP {response.status}')
                raw=bytearray()
                async for chunk in response.content.iter_chunked(65_536):
                    raw.extend(chunk)
                    if len(raw)>1_048_576:raise MusicError(f'{label}返回内容过大')
                try:data=json.loads(raw)
                except (ValueError,UnicodeDecodeError):raise MusicError(f'{label}返回的不是有效JSON') from None
                if not isinstance(data,dict):raise MusicError(f'{label}返回的数据结构不正确')
                return data
        except asyncio.TimeoutError:raise MusicError(f'{label}请求超时') from None
        except aiohttp.ClientError:raise MusicError(f'{label}暂时无法连接') from None

    async def search(self,keyword,limit):
        key=(self.settings.music_source,keyword.casefold(),limit)
        async with self.lock:
            now=time.monotonic()
            cached=self.cache.get(key)
            if cached and cached[0]>now:
                self.cache.move_to_end(key)
                return list(cached[1])
            if self.settings.music_source=='netease':songs=await self.search_netease(keyword,limit)
            else:songs=await self.search_qq(keyword,limit)
            if self.settings.cache_seconds:
                self.cache[key]=(time.monotonic()+self.settings.cache_seconds,tuple(songs))
                self.cache.move_to_end(key)
                while len(self.cache)>64:self.cache.popitem(last=False)
            return songs

    async def search_netease(self,keyword,limit):
        data=await self.request('GET',NETEASE_SEARCH,label='网易云音乐',
            params={'s':keyword,'type':1,'limit':limit,'offset':0},headers={'Referer':'https://music.163.com/'})
        if data.get('code',200)!=200:raise MusicError('网易云音乐暂时未接受搜索请求')
        found=(data.get('result') or {}).get('songs',[])
        if not isinstance(found,list):raise MusicError('网易云音乐返回的歌曲列表格式不正确')
        songs=[];seen=set()
        for row in found:
            if not isinstance(row,dict):continue
            sid=str(row.get('id') or '')
            if not sid.isdigit() or sid in seen or not row.get('name'):continue
            seen.add(sid)
            album=row.get('album') or row.get('al') or {}
            artists=row.get('artists') or row.get('ar') or []
            songs.append(Song('netease',sid,str(row['name']),
                ' / '.join(str(a['name']) for a in artists if isinstance(a,dict) and a.get('name')) or '未知歌手',
                f'https://music.163.com/#/song?id={sid}',str(album.get('name') or ''),
                int(row.get('duration') or row.get('dt') or 0)//1000,web_url(album.get('picUrl'))))
            if len(songs)==limit:break
        return songs

    async def search_qq(self,keyword,limit):
        module='music.search.SearchCgiService'
        envelope={'req_1':{'module':module,'method':'DoSearchForQQMusicDesktop',
            'param':{'query':keyword,'search_type':0,'page_num':1,'num_per_page':20}}}
        data=await self.request('POST',QQ_SEARCH,label='QQ音乐',body=envelope,
            headers={'Referer':'https://y.qq.com/'})
        if data.get('code',0)!=0:raise MusicError('QQ音乐暂时未接受搜索请求')
        result=data.get('req_1') or {}
        if result.get('code',0)!=0:raise MusicError('QQ音乐暂时未接受搜索请求')
        found=(((result.get('data') or {}).get('body') or {}).get('song') or {}).get('list',[])
        if not isinstance(found,list):raise MusicError('QQ音乐返回的歌曲列表格式不正确')
        songs=[];seen=set()
        for row in found:
            if not isinstance(row,dict):continue
            mid=str(row.get('mid') or row.get('songmid') or row.get('songMid') or '')
            title=row.get('name') or row.get('songname') or row.get('songName')
            if not mid or not mid.isalnum() or mid in seen or not title:continue
            seen.add(mid)
            album=row.get('album') if isinstance(row.get('album'),dict) else {}
            album_mid=str(album.get('mid') or row.get('albummid') or '')
            cover=f'https://y.gtimg.cn/music/photo_new/T002R300x300M000{album_mid}.jpg' if album_mid.isalnum() else ''
            songs.append(Song('qqmusic',mid,str(title),
                ' / '.join(str(a['name']) for a in row.get('singer',[]) if isinstance(a,dict) and a.get('name')) or '未知歌手',
                f'https://y.qq.com/n/ryqq/songDetail/{mid}',str(album.get('name') or row.get('albumname') or ''),
                int(row.get('interval') or 0),cover,card_id=str(row.get('songid') or row.get('id') or '')))
            if len(songs)==limit:break
        return songs

    async def extras(self,song):
        cover,audio=song.cover,song.audio
        if song.source!='netease':return cover,audio
        if not cover:
            data=await self.request('GET','https://music.163.com/api/song/detail/',label='歌曲封面',
                params={'ids':json.dumps([int(song.id)])})
            songs=data.get('songs') or []
            if songs:cover=web_url((songs[0].get('album') or {}).get('picUrl'))
        if not audio:
            data=await self.request('POST','https://music.163.com/api/song/enhance/player/url',label='公开播放地址',
                params={'id':song.id,'ids':json.dumps([int(song.id)]),'br':128000})
            rows=data.get('data') or []
            if rows:audio=web_url(rows[0].get('url'))
        return cover,audio

    async def signed_card(self,song):
        s=self.settings
        if not s.sign_api_url or not s.sign_api_key:raise MusicError('独立签名服务尚未填写地址或密钥')
        cover,audio=await self.extras(song)
        if not audio:raise MusicError('没有可用的公开音源，改用歌曲播放页面')
        response=await self.request('GET',s.sign_api_url,label='独立签名服务',params={
            'key':s.sign_api_key,'url':audio,'song':song.title,'singer':song.artist,
            'cover':cover,'jump':song.url,'format':s.sign_api_format or ('netease' if song.source=='netease' else 'qq')})
        data=response.get('data')
        if response.get('code')!=200 or not isinstance(data,dict) or not {'app','meta','prompt','view'}<=data.keys():
            raise MusicError('独立签名服务没有返回可发送的音乐卡片')
        if data['app']!='com.tencent.music.lua' or data['view']!='music':raise MusicError('独立签名服务返回的不是音乐卡片')
        if s.sign_api_key in json.dumps(data,ensure_ascii=False):raise MusicError('签名服务返回内容包含密钥，已停止发送')
        return data
