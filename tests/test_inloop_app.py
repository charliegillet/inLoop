"""Protect transcript attribution, GPS matching, and local workspace boundaries."""
import asyncio
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

from aiohttp.test_utils import TestClient, TestServer

from inloop_app import InLoop, Workspace, application


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'workspace.sqlite3'
        self.store=Workspace(self.path)

    def tearDown(self):
        self.store.db.close();self.temp.cleanup()

    def event(self,identity='one',text='Please test Bluetooth',said=1000):
        self.store.add_event(dict(type='transcript',event_id=identity,text=text,audio_start_at=said))
        return self.store.event(identity)

    def fix(self,recorded):
        return dict(latitude=37.7,longitude=-122.4,accuracy=12,recordedAt=recorded)

    def test_never_apply_a_future_fix_to_earlier_speech(self):
        self.store.add_fix(self.fix(1001),now=1002)
        self.assertIsNone(self.event(said=1000)['location'])
        self.store.add_fix(self.fix(997),now=1002)
        location=self.store.event('one')['location']
        self.assertEqual(location['age_at_speech_sec'],3)
        self.assertEqual(location['match'],'nearby_fix')

    def test_old_fix_and_invalid_coordinates_are_not_attached(self):
        self.store.add_fix(self.fix(300),now=1000)
        self.assertIsNone(self.event(said=1000)['location'])
        for value in [float('nan'),True,91]:
            self.assertFalse(self.store.add_fix({**self.fix(999),'latitude':value},now=1000))
        self.assertFalse(self.store.add_fix(self.fix(1010),now=1000))

    def test_final_replay_is_idempotent_partial_is_not_saved(self):
        self.event()
        self.event()
        self.assertFalse(self.store.add_event(dict(type='partial',event_id='draft',text='draft')))
        self.assertEqual(len(self.store.events()),1)

    def test_source_quote_and_session_must_match(self):
        self.event()
        with self.assertRaises(ValueError):
            self.store.add_task('Test',source_id='one',quote='invented quote')
        old=self.store.current
        self.store.new_session('Next')
        with self.assertRaises(ValueError):
            self.store.add_task('Test',source_id='one',quote='test Bluetooth')
        task=self.store.add_task('Test Bluetooth',session=old,source_id='one',quote='test Bluetooth')
        self.assertEqual(task['source_id'],'one')
        self.assertIsNone(self.store.add_task('Test Bluetooth!',session=old))
        with self.assertRaises(ValueError):self.store.add_task('Test',session='unknown')

    def test_saved_tasks_and_current_session_survive_restart(self):
        task=self.store.add_task('Test Bluetooth')
        self.store.update_task(task['id'],{'status':'done'})
        current=self.store.current
        self.store.db.close();self.store=Workspace(self.path)
        self.assertEqual(self.store.current,current)
        self.assertEqual(self.store.tasks()[0]['status'],'done')
        self.store.update_task(task['id'],{'deleted':True})
        self.assertEqual(self.store.tasks(),[])


class ApplicationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.workspace=InLoop(Path(self.temp.name)/'workspace.sqlite3')
        self.client=TestClient(TestServer(application(self.workspace,workers=False)))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.workspace.store.db.close();self.temp.cleanup()

    async def test_browser_mutation_requires_csrf_and_rejects_external_origin(self):
        response=await self.client.post('/api/tasks',json={'title':'Test'})
        self.assertEqual(response.status,403)
        headers={'X-inLoop-CSRF':self.workspace.nonce}
        response=await self.client.post('/api/tasks',json={'title':'Test'},headers=headers)
        self.assertEqual(response.status,200)
        response=await self.client.post('/api/tasks',json={'title':'Test'},headers={**headers,'Origin':'https://other.example'})
        self.assertEqual(response.status,403)
        response=await self.client.post('/api/tasks',json={'title':'Test','session_id':'unknown'},headers=headers)
        self.assertEqual(response.status,400)

    async def test_static_whitelist_does_not_serve_private_files(self):
        for path in ['/assets/vendor/leaflet.js','/assets/vendor/leaflet.css']:
            response=await self.client.get(path)
            self.assertEqual(response.status,200)
        for path in ['/assets/vendor/.env','/assets/.env','/.env']:
            response=await self.client.get(path)
            self.assertEqual(response.status,404)

    async def test_websocket_initial_state_and_new_final(self):
        socket=await self.client.ws_connect('/api/live')
        initial=await socket.receive_json()
        self.assertEqual(initial['type'],'state')
        self.assertNotIn('caption_token',initial['data'])
        self.workspace.store.add_event(dict(type='transcript',event_id='test',text='Live',audio_start_at=time.time()))
        await self.workspace.refresh()
        event=await socket.receive_json()
        self.assertEqual(event['data']['events'][0]['text'],'Live')
        await socket.close()

    async def test_github_projection_does_not_expose_tokens_or_arbitrary_urls(self):
        process=mock.Mock(returncode=0)
        process.communicate=mock.AsyncMock(return_value=(json.dumps([
            dict(title='Fix test',html_url='https://github.com/charliegillet/marshal/issues/12',number=12,user={'login':'user'},token='private'),
            dict(title='Bad',html_url='javascript:alert(1)')]).encode(),None))
        with mock.patch('inloop_app.shutil.which',return_value='/usr/bin/gh'),mock.patch('inloop_app.asyncio.create_subprocess_exec',new=mock.AsyncMock(return_value=process)) as run:
            rows=await self.workspace.read_github()
        self.assertEqual(len(rows),1)
        self.assertNotIn('token',rows[0])
        self.assertIn('q=is:open archived:false involves:yhinai',run.call_args.args)
        self.assertIn('per_page=20',run.call_args.args)

    async def test_github_timeout_kills_owned_process(self):
        process=mock.Mock()
        process.communicate=mock.AsyncMock()
        process.wait=mock.AsyncMock()
        async def timeout(awaitable,seconds):
            awaitable.close()
            self.assertEqual(seconds,12)
            raise TimeoutError()
        with mock.patch('inloop_app.shutil.which',return_value='/usr/bin/gh'),mock.patch('inloop_app.asyncio.create_subprocess_exec',new=mock.AsyncMock(return_value=process)),mock.patch('inloop_app.asyncio.wait_for',side_effect=timeout):
            with self.assertRaises(TimeoutError):await self.workspace.read_github()
        process.kill.assert_called_once()
        process.wait.assert_awaited_once()

    async def test_task_batch_keeps_each_session(self):
        store=self.workspace.store
        store.add_event(dict(type='transcript',event_id='old',text='Old task'))
        store.new_session('Next')
        store.add_event(dict(type='transcript',event_id='new',text='New task'))
        self.workspace.pending=['old','new'];self.workspace.changed.set()
        complete=asyncio.Event();calls=[]
        async def extract(identities):
            calls.append(identities)
            if len(calls)==2:complete.set()
        self.workspace.extract=extract
        job=asyncio.create_task(self.workspace.task_loop())
        try:
            await asyncio.wait_for(complete.wait(),4)
            self.assertEqual(calls,[['old'],['new']])
        finally:
            job.cancel()
            await asyncio.gather(job,return_exceptions=True)


if __name__=='__main__':unittest.main()
