"""音乐接口与回执离线验收；固定响应，不访问音乐、QQ或模型服务。"""
import asyncio,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
core=ROOT/'music_core' if (ROOT/'music_core').exists() else ROOT/'nonebot_plugin_simple_music/music_core'
if not core.exists():core=ROOT/'core/music_core'
sys.path.insert(0,str(core.parent))
from music_core import Settings,MusicClient,MusicService,MusicError
from music_core.models import Song

N={'code':200,'result':{'songs':[{'id':1,'name':'歌曲甲','artists':[{'name':'歌手甲'}],
   'album':{'name':'专辑甲','picUrl':'https://example.com/cover.jpg'},'duration':120000},
   {'id':1,'name':'重复','artists':[],'album':{}},{'id':2,'name':'歌曲乙','artists':[],'album':{}}]}}
Q={'code':0,'req_1':{'code':0,'data':{'body':{'song':{'list':[{'mid':'MID01','id':123,'name':'歌曲丙',
   'singer':[{'name':'歌手丙'}],'album':{'name':'专辑丙','mid':'ALBUM01'},'interval':180}]}}}}}

class Log:
    def __init__(self):self.messages=[]
    def warning(self,message):self.messages.append(message)

class Client(MusicClient):
    def __init__(self,settings,payload=N):super().__init__(settings);self.payload=payload;self.calls=[]
    async def request(self,method,url,**kwargs):
        self.calls.append((method,url,kwargs))
        if isinstance(self.payload,Exception):raise self.payload
        return self.payload
    async def extras(self,song):return song.cover,'https://example.com/audio.mp3'

class CoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_cache_limit_and_source(self):
        settings=Settings.from_mapping({});self.assertEqual(settings.send_mode,'link')
        client=Client(settings);songs=await client.search('歌曲',settings.limit())
        self.assertEqual(len(songs),2);self.assertEqual(songs[0].duration,'2:00')
        self.assertEqual(songs[0].url,'https://music.163.com/#/song?id=1')
        await client.search('歌曲',settings.limit());self.assertEqual(len(client.calls),1)
        await client.close();self.assertFalse(client.cache)
        qq=Client(Settings.from_mapping({'music_source':'qqmusic'}),Q)
        song=(await qq.search('歌曲',3))[0]
        self.assertEqual(song.id,'MID01');self.assertEqual(song.card_id,'123')
        self.assertIn('musicu.fcg',qq.calls[0][1])
        self.assertEqual(qq.calls[0][0],'POST')
        request=qq.calls[0][2]['body']['req_1']
        self.assertEqual(request['param']['num_per_page'],20)
        card=await MusicService(Settings.from_mapping({'send_mode':'card'}),qq,Log()).make_card(song)
        self.assertEqual(card.data,{'type':'qq','id':'123'})

    async def test_receipts_partial_and_no_hidden_model_calls(self):
        cfg=Settings.from_mapping({'send_mode':'card','card_count':2})
        client=Client(cfg);service=MusicService(cfg,client,Log());cards=[]
        async def send(card):cards.append(card);return False if len(cards)==1 else {'message_id':123}
        text=await service.recommend('歌曲',3,send)
        self.assertIn('确认发送 1 张音乐卡片：歌曲乙',text)
        self.assertIn('未成功发送：歌曲甲',text)
        self.assertEqual(len(client.calls),1);self.assertEqual(len(cards),2)
        async def unavailable(card):raise RuntimeError('fixture-secret should never leave this exception')
        text=await service.recommend('歌曲',3,unavailable)
        self.assertNotIn('fixture-secret',text);self.assertIn('未发送成功',text)
        self.assertIn('https://music.163.com/',text)

    async def test_disabled_empty_failure_and_settings(self):
        log=Log()
        async def send(card):raise AssertionError('unexpected send')
        disabled=Client(Settings.from_mapping({'enable_tool':False}))
        text=await MusicService(disabled.settings,disabled,log).recommend('歌曲',3,send)
        self.assertIn('关闭',text);self.assertFalse(disabled.calls)
        empty=Client(Settings(),{'code':200,'result':{}})
        self.assertIn('没有找到',await MusicService(empty.settings,empty,log).recommend('不存在',3,send))
        broken=Client(Settings(),MusicError('服务返回 HTTP 403'))
        self.assertIn('未完成',await MusicService(broken.settings,broken,log).recommend('歌曲',3,send))
        self.assertEqual(Settings.from_mapping({'send_mode':'ark'}).send_mode,'custom')
        self.assertEqual(Settings.from_mapping({'basic':{'send_mode':'card'}}).send_mode,'card')
        for value in (True,2.5,'bad'):
            with self.assertRaises(MusicError):Settings().limit(value)
        with self.assertRaises(MusicError):Settings.from_mapping({'sign_api_url':'http://example.com/'})

    async def test_signed_data_and_real_audio(self):
        cfg=Settings.from_mapping({'send_mode':'card_api','sign_api_url':'https://example.com/sign',
                                   'sign_api_key':'fixture-signing-key'})
        data={'code':200,'data':{'app':'com.tencent.music.lua','view':'music','prompt':'歌曲',
                              'meta':{'music':{'title':'歌曲甲'}}}}
        client=Client(cfg,data);song=Song('netease','1','歌曲甲','歌手','https://music.163.com/#/song?id=1')
        card=await MusicService(cfg,client,Log()).make_card(song)
        self.assertEqual(card.kind,'json');self.assertNotIn('fixture-signing-key',json.dumps(card.data))
        client.payload={'code':200,'data':{**data['data'],'extra':'fixture-signing-key'}}
        with self.assertRaises(MusicError):await client.signed_card(song)
        custom=MusicService(Settings.from_mapping({'send_mode':'custom'}),client,Log())
        card=await custom.make_card(song);self.assertEqual(card.data['audio'],'https://example.com/audio.mp3')
        self.assertNotIn('token',card.data)

    async def test_http_json_and_secrets(self):
        import aiohttp
        from aiohttp import web
        # 验证真实异步传输的分块读取和HTTP失败，不连接外部网络。
        async def ok(request):
            response=web.StreamResponse();await response.prepare(request)
            await response.write(b'{"code":');await asyncio.sleep(0)
            await response.write(b'200}');await response.write_eof();return response
        async def denied(request):return web.Response(status=403,text='fixture-signing-key')
        app=web.Application();app.router.add_get('/ok',ok);app.router.add_get('/bad',denied)
        runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
        port=runner.addresses[0][1];client=MusicClient(Settings())
        try:
            self.assertEqual(await client.request('GET',f'http://127.0.0.1:{port}/ok',label='测试服务'),{'code':200})
            with self.assertRaises(MusicError) as caught:
                await client.request('GET',f'http://127.0.0.1:{port}/bad',label='测试服务')
            self.assertNotIn('fixture-signing-key',str(caught.exception))
            session=client.session;await client.open();self.assertIs(client.session,session)
        finally:await client.close();await runner.cleanup()

if __name__=='__main__':unittest.main(verbosity=2)
