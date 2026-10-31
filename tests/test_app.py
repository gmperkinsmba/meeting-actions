import importlib.util
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from http.client import HTTPConnection
from pathlib import Path

TEMP = tempfile.TemporaryDirectory()
os.environ['MEETING_COMMITMENTS_DATA'] = TEMP.name
PATH = Path(__file__).parents[1] / 'server.py'
spec = importlib.util.spec_from_file_location('meeting_app', PATH)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.seed()
        cls.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        cls.server.daemon_threads = True
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        TEMP.cleanup()

    def request(self, method, path, obj=None, token=True, origin=None, host=None):
        c = HTTPConnection('127.0.0.1', self.port)
        headers = {'Content-Type':'application/json'}
        if token: headers['X-Local-Action'] = app.TOKEN
        if origin is not None: headers['Origin'] = origin
        if host: headers['Host'] = host
        body = json.dumps(obj) if obj is not None else None
        c.request(method, path, body, headers)
        r = c.getresponse(); data = r.read(); c.close()
        return r.status, json.loads(data) if data and r.getheader('Content-Type','').startswith('application/json') else data

    def test_source_refs_and_unresolved_tentative_conflict(self):
        text='[00:00:01] Ada: I will send the draft by 2026-11-01.\n[00:00:02] Bo: Actually the draft is due 2026-11-03.'
        found=app.proposals(text)
        self.assertEqual(found[0]['evidence'], {'line':1,'time':'00:00:01','speaker':'Ada','text':'I will send the draft by 2026-11-01.'})
        self.assertEqual(found[0]['status'],'unresolved')
        self.assertIn('conflict',found[0]['reason'])
        tentative=app.proposals('[00:00:03] Ada: Maybe I can finish the report Friday.')
        self.assertEqual(tentative[0]['status'],'unresolved')

    def test_boundary_rejects_wrong_origin_host_and_missing_token(self):
        path='/api/meetings'
        payload={'title':'Example','transcript':'[00:00:01] Ada: I will send a draft.'}
        self.assertEqual(self.request('POST',path,payload,token=False)[0],403)
        self.assertEqual(self.request('POST',path,payload,origin='https://evil.example')[0],403)
        self.assertEqual(self.request('GET','/',host='evil.example')[0],403)

    def test_import_confirm_export_filter_unknown_ids_and_bad_types(self):
        status,created=self.request('POST','/api/meetings',{'title':'XSS <img src=x>','transcript':'[00:00:01] Ada: I will send a draft by Friday.\n[00:00:02] Bo: I will schedule the review.'})
        self.assertEqual(status,201)
        state_status,state=self.request('GET','/api/state')
        self.assertEqual(state_status,200)
        item=next(x for x in state['items'] if x['text'].startswith('I will send'))
        self.assertEqual(item['evidence']['text'],'I will send a draft by Friday.')
        self.assertEqual(self.request('PATCH','/api/items/does-not-exist',{'owner':'Ada','due':'','status':'confirmed','resolved':True})[0],404)
        self.assertEqual(self.request('PATCH','/api/items/'+item['id'],[])[0],400)
        self.assertEqual(self.request('PATCH','/api/items/'+item['id'],{'owner':False,'due':'','status':'confirmed','resolved':True})[0],400)
        self.assertEqual(self.request('PATCH','/api/items/'+item['id'],{'owner':'Ada','due':'','status':'confirmed','resolved':False})[0],400)
        self.assertEqual(self.request('PATCH','/api/items/'+item['id'],{'owner':'Ada','due':'','status':'confirmed','resolved':True})[0],200)
        out=self.request('GET',f"/api/meetings/{created['id']}/export")[1]
        self.assertEqual(len(out['items']),1)
        self.assertEqual(out['items'][0]['evidence']['text'],item['evidence']['text'])

    def test_unresolved_item_needs_edit_save_before_confirmation(self):
        _,created=self.request('POST','/api/meetings',{'title':'Tentative','transcript':'[00:00:01] Ada: Maybe I can send the draft by Friday.'})
        _,state=self.request('GET','/api/state?id='+created['id'])
        item=state['items'][0]
        self.assertEqual(item['status'],'unresolved')
        self.assertEqual(self.request('PATCH','/api/items/'+item['id'],{'owner':'Ada','due':'Friday','status':'confirmed','resolved':True})[0],400)
        self.assertEqual(self.request('PATCH','/api/items/'+item['id'],{'owner':'Ada','due':'Friday','status':'proposed','resolved':True})[0],200)
        self.assertEqual(self.request('PATCH','/api/items/'+item['id'],{'owner':'Ada','due':'Friday','status':'confirmed','resolved':True})[0],200)

    def test_bad_imports_are_rejected_without_creating_meeting(self):
        before=len(self.request('GET','/api/state')[1]['items'])
        self.assertEqual(self.request('POST','/api/meetings',{'title':True,'transcript':'[00:00:01] Ada: words'})[0],400)
        self.assertEqual(self.request('POST','/api/meetings',{'title':'Bad','transcript':'no speaker time'})[0],400)
        after=len(self.request('GET','/api/state')[1]['items'])
        self.assertEqual(before,after)

    def test_user_text_is_html_escaped_and_no_remote_fonts(self):
        self.assertIn("'&lt;'",app.JS)
        self.assertIn("'&#39;'",app.JS)
        self.assertNotIn('fonts.googleapis.com',app.CSS)
        self.assertIn("default-src 'self'",__import__('inspect').getsource(app.Handler.send))

    def test_database_connection_closes_when_setup_fails(self):
        connection=Mock()
        connection.execute.side_effect=RuntimeError('injected setup failure')
        with patch.object(app,'prepare_database'), patch.object(app.sqlite3,'connect',return_value=connection):
            with self.assertRaisesRegex(RuntimeError,'injected setup failure'):
                app.connect()
        connection.close.assert_called_once_with()

if __name__=='__main__':
    unittest.main()
