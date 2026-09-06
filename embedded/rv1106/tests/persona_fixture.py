"""Test-only deterministic clock and HTTP boundary; never loaded by production."""
import contextlib
from datetime import datetime as RealDatetime
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from agent_core.headless import create_manager, serve
import requests

class Clock(RealDatetime):
    value = RealDatetime(2026, 1, 30, 12)
    @classmethod
    def now(cls, tz=None):
        return cls.value if tz is None else cls.value.astimezone(tz)

def factory(settings):
    root = Path(settings["data_dir"])
    def post(url, *, headers, json, **kwargs):
        with (root / "calls.jsonl").open("a", encoding="utf-8") as log:
            log.write(__import__('json').dumps({'url':url, 'body':json}, ensure_ascii=False)+'\n')
        failure = os.environ.get("TEST_FAILURE")
        if failure == "network": raise requests.ConnectionError("secret-must-not-leak")
        if failure == "auth": raise requests.HTTPError("secret-must-not-leak")
        if failure == "exit": os._exit(9)
        if failure == "timeout": time.sleep(10)
        if json.get('stream'):
            answer = "谢谢你的信任，我会陪着你。"
        else:
            answer = __import__('json').dumps({"summary_text":"用户喜欢茉莉花茶，互相支持。",
                "topics":["茉莉花茶"], "user_preferences":["喜欢茉莉花茶"],
                "important_messages":[], "emotional_tone":"positive", "unfinished_topics":[],
                "key_events":[], "important_memories":[], "relationship_changes":"更熟悉"}, ensure_ascii=False)
        class Response:
            def raise_for_status(self): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def json(self):
                return {"id":"fixture", "model":"qwen-plus", "choices":[{"message":{"role":"assistant","content":answer},"finish_reason":"stop"}]}
            def iter_lines(self):
                yield ('data: '+__import__('json').dumps({"choices":[{"delta":{"content":answer}}]})).encode()
                if failure != "partial": yield b'data: [DONE]'
        return Response()
    requests.post = post
    manager = create_manager(settings)
    original = manager.send_message_stream
    def send(message, **kwargs):
        date, text = message.split('|',1)
        Clock.value = RealDatetime.fromisoformat(date)
        yield from original(text, **kwargs)
    manager.send_message_stream = send
    return manager

def run():
    for name, module in list(sys.modules.items()):
        if name.startswith('agent_core.') and getattr(module, 'datetime', None) is RealDatetime:
            module.datetime = Clock
    with patch('time.time', side_effect=lambda: Clock.value.timestamp()):
        sink = sys.stdout
        with open(os.devnull, 'w') as discard, contextlib.redirect_stdout(discard), contextlib.redirect_stderr(discard):
            if os.environ.get('TEST_DIRECT'):
                settings=json.loads(sys.stdin.readline())
                manager=factory(settings)
                for message in sys.stdin:
                    events=list(manager.send_message_stream(message.rstrip('\n'), allow_sync_fallback=False))
                    assert events[-1]['type']=='done', events
                    sink.write(events[-1]['content']+'\n')
                    sink.flush()
                return 0
            return serve(sys.stdin, sink, factory)

if __name__ == '__main__': raise SystemExit(run())
