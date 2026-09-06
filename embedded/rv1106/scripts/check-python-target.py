"""Run on RV1106 after installing the staged overlay; does not call an LLM."""
import ctypes
import fcntl
import json
import platform
import ssl
import struct
import sys
import requests
import agent_core.headless

assert sys.version_info >= (3,11)
assert struct.calcsize('P') == 4, 'requires 32-bit target'
assert platform.machine().startswith(('arm','aarch')), 'requires ARM target'
context=ssl.create_default_context(cafile=requests.certs.where())
assert context.get_ca_certs(), 'CA bundle missing'
print(json.dumps({'imports':'ok','tls':ssl.OPENSSL_VERSION,'pointer_bits':32,
    'gui_loaded':any(name in sys.modules for name in ('flet','PIL')),
    'board_resources':'measure separately'}))
