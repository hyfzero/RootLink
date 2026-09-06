"""Run with the project .venv after building rootlink_persona_bridge_driver."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
DRIVER = Path(os.environ.get('PERSONA_TEST_DRIVER', BASE/'build/simulator-alsa-cloud/rootlink_persona_bridge_driver'))
FIXTURE = HERE/'persona_fixture.py'

def normalized(value):
    if isinstance(value, dict):
        return {k: normalized(v) for k,v in value.items() if k not in
                {'timestamp','created_at','updated_at','last_updated','relationship_updated_at'}}
    if isinstance(value, list): return [normalized(v) for v in value]
    if isinstance(value, str): return re.sub(r'msg_\d{13}', 'msg_fixed', value)
    return value

def snapshot(root):
    result={}
    for p in root.rglob('*'):
        if p.is_file() and p.suffix in ('.json','.jsonl','.md'):
            text=p.read_text()
            result[str(p.relative_to(root))]=normalized(json.loads(text) if p.suffix=='.json' else
                [json.loads(line) for line in text.splitlines()] if p.suffix=='.jsonl' else text)
    return result

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.seed=self.root/'seed'
        shutil.copytree(BASE/'config/role-example',self.seed)
        config=json.loads((self.seed/'config.json').read_text())
        config['history']={'max_context_tokens':300,'token_reserved':100}
        (self.seed/'config.json').write_text(json.dumps(config))
        memories=json.loads((self.seed/'memories.json').read_text())
        memories['preference_memories']=[{'id':'seed-preference','content':'用户喜欢雨后松木的气味',
            'timestamp':1769731200,'memory_type':'preference','importance':2.0,'context':'气味'}]
        (self.seed/'memories.json').write_text(json.dumps(memories,ensure_ascii=False))
    def tearDown(self): self.tmp.cleanup()
    def invoke(self, data, messages, direct=False, **env):
        settings={'data_dir':str(data),'role_dir':str(self.seed),'model':{'name':'qwen-plus','provider':'qwen',
            'base_url':'https://dashscope.aliyuncs.com/compatible-mode/v1','api_key':''}}
        command=[sys.executable,str(FIXTURE)] if direct else [str(DRIVER),sys.executable,str(FIXTURE),str(self.seed),str(data)]
        payload=('' if not direct else json.dumps(settings)+'\n')+'\n'.join(messages)+'\n'
        return subprocess.run(command,input=payload,text=True,capture_output=True,timeout=20,
            env={**os.environ,**({'TEST_DIRECT':'1'} if direct else {}),**env})
    def test_parity_multiturn_restart_day_month(self):
        direct=self.root/'direct'; bridge=self.root/'bridge'
        phases=[['2026-01-30T12:00:00|你好，我喜欢茉莉花茶。',
                 '2026-01-30T12:01:00|谢谢你，我信任你。',
                 '2026-01-31T12:00:00|今天很难过，请陪我。',
                 '2026-01-31T12:01:00|记得我喜欢什么茶吗？'],
                ['2026-01-31T12:02:00|继续刚才的话题。',
                 '2026-02-01T12:00:00|新的月份开始了。']]
        for messages in phases:
            a=self.invoke(direct,messages,True); b=self.invoke(bridge,messages)
            self.assertEqual(a.returncode,0,a.stderr)
            self.assertEqual(b.returncode,0,b.stderr)
            self.assertEqual(a.stdout,b.stdout)
            self.assertEqual(snapshot(direct),snapshot(bridge))
        saved=snapshot(bridge)
        self.assertTrue(any('monthly.json' in key for key in saved))
        self.assertTrue(any('summary.json' in key for key in saved))
        state=saved['default/persona/state.json']
        self.assertGreater(state['familiarity'],0)
        calls=saved['calls.jsonl']
        self.assertGreater(len(calls),6) # summaries use the same adapter too
        self.assertTrue(any('茉莉花茶' in json.dumps(c['body'],ensure_ascii=False) for c in calls))
        self.assertIn('雨后松木',json.dumps(calls[0]['body']['messages'],ensure_ascii=False))
    def test_failures_no_replay(self):
        for failure in ('auth','network','exit','timeout','partial'):
            with self.subTest(failure=failure):
                data=self.root/failure
                result=self.invoke(data,['2026-01-30T12:00:00|你好'],TEST_FAILURE=failure,TEST_TIMEOUT='1500')
                self.assertNotEqual(result.returncode,0)
                self.assertNotIn('secret-must-not-leak',result.stdout+result.stderr)
                self.assertEqual(result.stdout,'')
                calls=(data/'calls.jsonl').read_text().splitlines()
                self.assertEqual(len(calls),1)
                for path in (data/'default/history').rglob('*.json'):
                    self.assertNotIn('谢谢你的信任',path.read_text())
    def test_history_budget_parity(self):
        messages=[f'2026-01-30T12:{i:02d}:00|MARKER_{i:02d} '+('普通对话内容。'*40) for i in range(12)]
        direct=self.root/'budget-direct'; bridge=self.root/'budget-bridge'
        a=self.invoke(direct,messages,True); b=self.invoke(bridge,messages)
        self.assertEqual(a.returncode,0,a.stderr)
        self.assertEqual(b.returncode,0,b.stderr)
        self.assertEqual(snapshot(direct),snapshot(bridge))
        calls=snapshot(bridge)['calls.jsonl']
        last=calls[-1]['body']['messages']
        self.assertNotIn('MARKER_00',json.dumps(last,ensure_ascii=False))
        self.assertIn('MARKER_11',json.dumps(last,ensure_ascii=False))
    def test_model_transport_mapping(self):
        sys.path.insert(0,str(BASE.parents[1]/'src'))
        from agent_core.headless import create_manager
        settings={'data_dir':str(self.root/'mapping'),'role_dir':str(self.seed),'llm_timeout_ms':12345,
            'model':{'name':'model-custom','provider':'qwen','base_url':'https://example.invalid/v1/',
                     'api_key':'resolved-test-key','headers':{'Authorization':'stale-key','X-Test':'ok'},
                     'auth_header':True,'chat_path':'/custom-chat'}}
        manager=create_manager(settings)
        agent=manager.chat_agent
        self.assertEqual(agent.config.name,'model-custom')
        self.assertEqual(agent.config.resolved_base_url,'https://example.invalid/v1')
        self.assertEqual(agent.chat_path,'/custom-chat')
        self.assertEqual(agent.request_timeout,12.345)
        self.assertEqual(agent._request_headers()['authorization'],'Bearer resolved-test-key')
        self.assertEqual(agent._request_headers()['x-test'],'ok')
        agent.auth_header=False
        self.assertEqual(agent._request_headers()['authorization'],'stale-key')
        self.assertFalse(manager.tools)
    def test_invalid_protocol_and_start_timeout(self):
        for script in ('print("invalid",flush=True)', 'import time; time.sleep(10)',
                       'print(\'{"v":2,"id":1,"event":"ready"}\',flush=True)'):
            worker=self.root/'broken.py'; worker.write_text(script)
            result=subprocess.run([str(DRIVER),sys.executable,str(worker),str(self.seed),str(self.root/'bad')],
                capture_output=True,timeout=5,env={**os.environ,'TEST_TIMEOUT':'100'})
            self.assertNotEqual(result.returncode,0)
    def test_worker_lock_health_shutdown_and_bad_id(self):
        worker=BASE/'scripts/persona-worker.py'
        settings={'data_dir':str(self.root/'locked'),'role_dir':str(self.seed),'model':{
            'name':'qwen-plus','provider':'qwen','base_url':'https://example.invalid','api_key':'secret-must-not-leak'}}
        def request(process, value):
            process.stdin.write(json.dumps(value)+'\n'); process.stdin.flush()
            return json.loads(process.stdout.readline())
        with subprocess.Popen([sys.executable,str(worker)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,text=True) as first:
            self.assertEqual(request(first,{'v':1,'id':1,'op':'init','settings':settings})['event'],'ready')
            second=subprocess.run([sys.executable,str(worker)],input=json.dumps({'v':1,'id':1,'op':'init','settings':settings})+'\n',
                text=True,capture_output=True,timeout=5)
            self.assertNotEqual(second.returncode,0)
            self.assertNotIn('secret-must-not-leak',second.stdout+second.stderr)
            self.assertEqual(request(first,{'v':1,'id':2,'op':'health'})['event'],'ready')
            self.assertEqual(request(first,{'v':1,'id':3,'op':'shutdown'})['event'],'done')
            self.assertEqual(first.wait(timeout=5),0)
        bad=subprocess.run([sys.executable,str(worker)],input='{"v":1,"id":0,"op":"health"}\n',
            text=True,capture_output=True,timeout=5)
        self.assertNotEqual(bad.returncode,0)
        self.assertEqual(json.loads(bad.stdout)['event'],'error')

if __name__=='__main__': unittest.main()
