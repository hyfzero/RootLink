"""Opt-in WSLg/cloud integration using recorded microphone audio and real Pulse playback.

ALSA's file plugin substitutes recorded samples, while Pulse capture supplies the
clock. No global sound configuration is modified. Run with the project .venv.
"""
import argparse
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time
import wave

parser = argparse.ArgumentParser()
parser.add_argument('--voice', type=Path, required=True)
parser.add_argument('--config', type=Path, required=True)
parser.add_argument('--input', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--allow-cloud', action='store_true', required=True)
args = parser.parse_args()
root = args.output.resolve()
root.mkdir(mode=0o700)  # New directory prevents mixing test histories.
with wave.open(str(args.input)) as wav:
    assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 16000)
    raw = bytes(32000) + wav.readframes(wav.getnframes()) + bytes(32000 * 30)
(root / 'capture.raw').write_bytes(raw)
(root / 'alsa.conf').write_text('</usr/share/alsa/alsa.conf>\n' +
    'pcm.rootlink_recorded { type file slave.pcm "pulse" file "/dev/null" format "raw" infile ' +
    json.dumps(str(root / 'capture.raw')) + ' }\n')
env = {**os.environ, 'ALSA_CONFIG_PATH': str(root / 'alsa.conf'),
       'CAPTURE_DEVICE': 'rootlink_recorded', 'PLAYBACK_DEVICE': 'pulse',
       'UI_BACKEND': 'sdl', 'PYTHON_DATA_DIR': str(root / 'persona-data')}
states = []
log = []
deadline = time.monotonic() + 120
with subprocess.Popen(['stdbuf', '-oL', str(args.voice.resolve()), 'voice', '--config',
                       str(args.config.resolve())], env=env, stdout=subprocess.PIPE,
                      stderr=subprocess.STDOUT, bufsize=0) as process:
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    pending = b''
    try:
        while process.poll() is None and time.monotonic() < deadline:
            for key, _ in selector.select(0.2):
                chunk = os.read(key.fileobj.fileno(), 4096)
                pending += chunk
                while b'\n' in pending:
                    line, pending = pending.split(b'\n', 1)
                    text = line.decode('utf-8', errors='replace')
                    log.append(text)
                    # Streaming answer text can precede the next state on the same line.
                    if 'state=' in text:
                        state = text.rsplit('state=', 1)[1].strip()
                        states.append(state)
                        if state == 'ERROR' or (state == 'LISTENING' and 'PLAYING' in states):
                            process.send_signal(signal.SIGINT)
                            deadline = min(deadline, time.monotonic() + 10)
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            process.wait(timeout=10)
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
            process.wait()
    exit_code = process.returncode
expected = ['IDLE', 'LISTENING', 'TRANSCRIBING', 'THINKING', 'SYNTHESIZING',
            'PLAYING', 'IDLE', 'LISTENING']
result = {'recorded_input': True, 'service_mode': 'cloud', 'playback_device': 'pulse',
          'states': states, 'exit_code': exit_code,
          'passed': states[:len(expected)] == expected and exit_code == 0}
(root / 'result.json').write_text(json.dumps(result, indent=2))
# Private transcript output is kept locally, never printed by this test.
fd = os.open(root / 'voice.log', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as stream:
    stream.write('\n'.join(log))
print(json.dumps(result))
raise SystemExit(0 if result['passed'] else 1)
