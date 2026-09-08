import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "enroll-cosyvoice.py"
spec = importlib.util.spec_from_file_location("enroll_cosyvoice", SCRIPT)
enroll = importlib.util.module_from_spec(spec)
spec.loader.exec_module(enroll)


class FakeService:
    def __init__(self, states=("OK",)):
        self.states = list(states)
        self.created = []
        self.queried = []

    def create_voice(self, **kwargs):
        self.created.append(kwargs)
        return "cosyvoice-v3.5-plus-voice-created"

    def query_voice(self, voice_id):
        self.queried.append(voice_id)
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return {"status": state}


class EnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.secrets = self.root / "secrets.env"
        self.secrets.write_text("DASHSCOPE_API_KEY=file-key\n", encoding="utf-8")
        self.output = self.root / "voice.json"

    def tearDown(self):
        self.temp.cleanup()

    def args(self, *extra):
        return enroll.build_parser().parse_args([
            "--audio-url", "https://audio.example.test/sample.wav",
            "--secrets-file", str(self.secrets), "--output", str(self.output),
            "--timeout", "20", *extra,
        ])

    def test_success_writes_id_before_poll_and_config(self):
        service = FakeService(("PROCESSING", "OK"))
        now = [0.0]

        def sleep(seconds):
            now[0] += seconds

        with mock.patch("sys.stdout") as stdout:
            self.assertEqual(enroll.run(self.args(), service_factory=lambda *_: service,
                                        clock=lambda: now[0], sleeper=sleep), 0)
            printed = "".join(call.args[0] for call in stdout.write.call_args_list)
        self.assertIn("TTS_MODEL=cosyvoice-v3.5-plus", printed)
        self.assertIn("TTS_VOICE=cosyvoice-v3.5-plus-voice-created", printed)
        data = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(data["voice_id"], "cosyvoice-v3.5-plus-voice-created")
        self.assertEqual(data["TTS_MODEL"], "cosyvoice-v3.5-plus")
        self.assertEqual(data["TTS_VOICE"], "cosyvoice-v3.5-plus-voice-created")
        self.assertEqual(service.created[0]["language_hints"], ["ja"])

    def test_failed_terminal_state_is_reported(self):
        service = FakeService(("UNDEPLOYED",))
        with self.assertRaises(enroll.EnrollmentError):
            enroll.run(self.args(), service_factory=lambda *_: service)
        self.assertEqual(json.loads(self.output.read_text())["status"], "UNDEPLOYED")

    def test_poll_timeout_is_bounded(self):
        service = FakeService(("PROCESSING",))
        now = [0.0]

        def sleep(seconds):
            now[0] += seconds

        with self.assertRaises(enroll.EnrollmentError):
            enroll.run(self.args("--timeout", "1"), service_factory=lambda *_: service,
                       clock=lambda: now[0], sleeper=sleep)
        self.assertEqual(json.loads(self.output.read_text())["status"], "TIMEOUT")

    def test_resume_does_not_create_duplicate(self):
        self.output.write_text(json.dumps({"voice_id": "cosyvoice-v3.5-plus-existing", "status": "PENDING"}))
        service = FakeService(("OK",))
        args = enroll.build_parser().parse_args([
            "--voice-id", "cosyvoice-v3.5-plus-existing", "--secrets-file", str(self.secrets),
            "--output", str(self.output),
        ])
        enroll.run(args, service_factory=lambda *_: service)
        self.assertEqual(service.created, [])
        self.assertEqual(service.queried, ["cosyvoice-v3.5-plus-existing"])

    def test_resume_rejects_mismatched_model_or_prefix(self):
        self.output.write_text(json.dumps({"voice_id": "existing", "model": "other-model",
                                           "prefix": "amadeus"}))
        args = enroll.build_parser().parse_args([
            "--voice-id", "existing", "--secrets-file", str(self.secrets),
            "--output", str(self.output),
        ])
        with self.assertRaises(enroll.EnrollmentError):
            enroll.run(args, service_factory=lambda *_: FakeService())
        self.output.write_text(json.dumps({"voice_id": "existing", "model": args.model,
                                           "target_model": args.model, "prefix": "different"}))
        args = enroll.build_parser().parse_args([
            "--voice-id", "existing", "--secrets-file", str(self.secrets),
            "--output", str(self.output),
        ])
        with self.assertRaises(enroll.EnrollmentError):
            enroll.run(args, service_factory=lambda *_: FakeService())

    def test_voice_id_must_be_bound_to_model(self):
        self.output.write_text(json.dumps({"voice_id": "other-model-existing", "status": "PENDING"}))
        args = enroll.build_parser().parse_args([
            "--voice-id", "other-model-existing", "--secrets-file", str(self.secrets),
            "--output", str(self.output),
        ])
        with self.assertRaises(enroll.EnrollmentError):
            enroll.run(args, service_factory=lambda *_: FakeService())
        service = FakeService(("OK",))
        service.create_voice = lambda **kwargs: "wrong-model-id"
        with self.assertRaises(enroll.EnrollmentError):
            enroll.run(self.args(), service_factory=lambda *_: service)

    def test_query_target_model_must_match(self):
        service = FakeService(("OK",))
        service.query_voice = lambda _: {"status": "OK", "target_model": "other-model"}
        with self.assertRaises(enroll.EnrollmentError):
            enroll.run(self.args(), service_factory=lambda *_: service)
    def test_nonfinite_timeout_is_rejected(self):
        with self.assertRaises(enroll.EnrollmentError):
            enroll.run(self.args("--timeout", "nan"), service_factory=lambda *_: FakeService())

    def test_existing_output_refuses_new_enrollment(self):
        self.output.write_text(json.dumps({"voice_id": "existing"}))
        with self.assertRaises(enroll.EnrollmentError):
            enroll.run(self.args(), service_factory=lambda *_: FakeService())

    def test_environment_key_has_priority_and_is_never_leaked(self):
        service = FakeService(("OK",))
        with mock.patch.dict(os.environ, {"DASHSCOPE_API_KEY": "environment-key"}):
            seen = {}
            def factory(key, _):
                seen["key"] = key
                return service
            enroll.run(self.args(), service_factory=factory)
        self.assertEqual(seen["key"], "environment-key")

    def test_validation_rejects_untrusted_base_and_non_https_audio(self):
        with self.assertRaises(enroll.EnrollmentError):
            enroll.run(self.args("--base-url", "https://evil.example/api"),
                       service_factory=lambda *_: FakeService())
        with self.assertRaises(enroll.EnrollmentError):
            enroll.run(self.args("--audio-url", "http://audio.example/sample.wav"),
                       service_factory=lambda *_: FakeService())

    def test_workspace_base_host_is_allowed_without_userinfo_or_arbitrary_port(self):
        service = FakeService(("OK",))
        args = self.args("--base-url", "https://my-workspace.cn-beijing.maas.aliyuncs.com/api/v1")
        enroll.run(args, service_factory=lambda *_: service)
        with self.assertRaises(enroll.EnrollmentError):
            enroll.run(self.args("--base-url", "https://user:pass@dashscope.aliyuncs.com/api/v1"),
                       service_factory=lambda *_: FakeService())
        with self.assertRaises(enroll.EnrollmentError):
            enroll.run(self.args("--base-url", "https://dashscope.aliyuncs.com:8443/api/v1"),
                       service_factory=lambda *_: FakeService())


if __name__ == "__main__":
    unittest.main()
