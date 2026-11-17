import os
import stat
import sys
import unittest
from pathlib import Path
from unittest import mock

from factory.core.config import FactoryError
from factory.modules.production import create_project
from factory.voice_studio import audio, clones, service
from factory.voice_studio.engines import get_engine
from factory.voice_studio.engines.base import EngineNotConfigured, PaidAPIDisabled
from tests.helpers import make_sandbox, make_wav, remove_sandbox, write_script

YES = lambda message: True   # noqa: E731
NO = lambda message: False   # noqa: E731


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.ctx = make_sandbox()
        self.p = create_project(self.ctx, "Voice test", "en", "psychology", "short", created="2026-01-01")
        write_script(self.ctx, self.p)
        self.vdir = self.p.folder / "05_voice"

    def tearDown(self):
        remove_sandbox(self.tmp)

    def files_in(self, sub):
        return [f for f in (self.vdir / sub).iterdir() if f.name != ".gitkeep"]


class TestRecorderAndAudio(Base):
    def test_import_keeps_protected_original(self):
        src = make_wav(self.tmp / "in/take.wav", 3)
        item = service.import_audio(self.ctx, self.p, src, note="first")
        self.assertEqual((item["id"], item["kind"], item["take"]), ("A001", "raw", 1))
        self.assertAlmostEqual(item["duration_sec"], 3.0, places=2)
        dest = self.vdir / item["file"]
        self.assertTrue(dest.exists())
        if os.name == "posix":
            self.assertFalse(dest.stat().st_mode & stat.S_IWUSR)  # read-only original
        retake = service.import_audio(self.ctx, self.p, src)
        self.assertEqual(retake["take"], 2)
        self.assertNotEqual(retake["file"], item["file"])

    def test_import_rejects_unsupported_and_missing(self):
        bad = self.tmp / "x.ogg"
        bad.write_bytes(b"x")
        with self.assertRaises(FactoryError):
            service.import_audio(self.ctx, self.p, bad)
        with self.assertRaises(FactoryError):
            service.import_audio(self.ctx, self.p, self.tmp / "nope.wav")

    def test_mp3_and_m4a_accepted(self):
        for name in ("a.mp3", "b.m4a"):
            f = self.tmp / name
            f.write_bytes(b"\x00" * 100)
            self.assertEqual(service.import_audio(self.ctx, self.p, f)["format"], name[-3:])

    def test_trim_creates_new_file_and_original_untouched(self):
        raw = service.import_audio(self.ctx, self.p, make_wav(self.tmp / "t.wav", 4))
        before = (self.vdir / raw["file"]).read_bytes()
        edited = service.trim_audio(self.ctx, self.p, raw["id"], 1.0, 2.5)
        self.assertEqual(edited["kind"], "edited")
        self.assertEqual(edited["parent"], raw["id"])
        self.assertAlmostEqual(edited["duration_sec"], 1.5, places=2)
        self.assertEqual((self.vdir / raw["file"]).read_bytes(), before)
        with self.assertRaises(FactoryError):
            service.trim_audio(self.ctx, self.p, raw["id"], 3, 2)

    def test_record_without_any_recorder(self):
        with mock.patch("shutil.which", return_value=None):
            with self.assertRaises(audio.AudioToolMissing):
                service.record_take(self.ctx, self.p, 5)

    def test_record_uses_backend(self):
        def fake_run(cmd, *a, **k):
            make_wav(Path(cmd[cmd.index("-d") + 2]) if "-d" in cmd else Path(cmd[-1]), 1)
            return mock.Mock(returncode=0)
        with mock.patch("shutil.which", side_effect=lambda t: "/bin/arecord" if t == "arecord" else None), \
                mock.patch("subprocess.run", side_effect=fake_run):
            item = service.record_take(self.ctx, self.p, 1)
        self.assertEqual(item["source_file"], "microphone")


class TestAIVoices(Base):
    def test_tts_mock_uses_script_narration(self):
        item = service.text_to_speech(self.ctx, self.p)
        self.assertEqual((item["kind"], item["engine"], item["voice"]), ("tts", "mock", "female-documentary"))
        self.assertTrue((self.vdir / item["file"]).exists())
        self.assertGreater(item["duration_sec"], 1)

    def test_tts_language_check(self):
        presets = self.ctx.config.voice_presets
        presets["female-soft"]["languages"] = ["ms"]
        with self.assertRaises(FactoryError):
            service.text_to_speech(self.ctx, self.p, voice="female-soft")
        with self.assertRaises(FactoryError):
            service.text_to_speech(self.ctx, self.p, voice="robot-voice")

    def test_convert_preserves_length_and_requires_own_recording(self):
        raw = service.import_audio(self.ctx, self.p, make_wav(self.tmp / "t.wav", 2.5))
        conv = service.convert_voice(self.ctx, self.p, raw["id"], "male-deep")
        self.assertEqual((conv["kind"], conv["parent"]), ("converted", raw["id"]))
        self.assertAlmostEqual(conv["duration_sec"], 2.5, places=2)
        tts = service.text_to_speech(self.ctx, self.p)
        with self.assertRaises(FactoryError):
            service.convert_voice(self.ctx, self.p, tts["id"], "male-deep")

    def test_select_and_export(self):
        tts = service.text_to_speech(self.ctx, self.p)
        with self.assertRaises(FactoryError):
            service.export_audio(self.ctx, self.p)  # nothing selected
        service.select(self.ctx, self.p, tts["id"])
        exp = service.export_audio(self.ctx, self.p, fmt="wav")
        self.assertEqual((exp["kind"], exp["parent"]), ("export", tts["id"]))
        with self.assertRaises(FactoryError):
            service.select(self.ctx, self.p, exp["id"])
        with self.assertRaises(FactoryError):
            service.export_audio(self.ctx, self.p, fmt="flac")

    @unittest.skipUnless(audio.has_ffmpeg(), "FFmpeg not installed")
    def test_export_mp3_with_ffmpeg(self):
        tts = service.text_to_speech(self.ctx, self.p)
        exp = service.export_audio(self.ctx, self.p, tts["id"], fmt="mp3")
        self.assertTrue((self.vdir / exp["file"]).name.endswith(".mp3"))

    def test_mp3_export_without_ffmpeg_explains(self):
        tts = service.text_to_speech(self.ctx, self.p)
        with mock.patch("shutil.which", return_value=None):
            with self.assertRaises(audio.AudioToolMissing):
                service.export_audio(self.ctx, self.p, tts["id"], fmt="mp3")

    def test_history_across_projects(self):
        service.text_to_speech(self.ctx, self.p)
        rows = service.history(self.ctx)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0][2])


class TestElevenLabsSafety(Base):
    def setUp(self):
        super().setUp()
        self.ctx.config.voice_presets["female-documentary"]["engine_voices"]["elevenlabs"]["voice_id"] = "VOICE123"

    def test_external_engine_needs_confirmation(self):
        with self.assertRaises(FactoryError) as e:
            service.text_to_speech(self.ctx, self.p, engine_name="elevenlabs", confirm=NO)
        self.assertIn("Cancelled", str(e.exception))
        self.assertEqual(self.files_in("tts"), [])
        raw = service.import_audio(self.ctx, self.p, make_wav(self.tmp / "t.wav", 1))
        with self.assertRaises(FactoryError):
            service.convert_voice(self.ctx, self.p, raw["id"], "female-documentary",
                                  engine_name="elevenlabs", confirm=NO)

    def test_default_confirm_is_no(self):
        with self.assertRaises(FactoryError):
            service.text_to_speech(self.ctx, self.p, engine_name="elevenlabs")

    def test_mock_engine_never_asks(self):
        asked = []
        service.text_to_speech(self.ctx, self.p, confirm=lambda m: asked.append(m))
        self.assertEqual(asked, [])

    def test_missing_key_then_paid_calls_disabled(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(EngineNotConfigured):
                service.text_to_speech(self.ctx, self.p, engine_name="elevenlabs", confirm=YES)
        with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": "secret-test-key"}):
            with self.assertRaises(PaidAPIDisabled):
                service.text_to_speech(self.ctx, self.p, engine_name="elevenlabs", confirm=YES)
        self.assertEqual(self.files_in("tts"), [])
        self.assertEqual(service.audio_log(self.ctx, self.p).items, [])

    def test_request_never_contains_key_value(self):
        engine = get_engine(self.ctx, "elevenlabs")
        with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": "secret-test-key"}):
            req = engine.build_tts_request("Hai semua", "VOICE123", "ms", {"stability": 0.5, "foo": 1})
        self.assertNotIn("secret-test-key", repr(req))
        self.assertTrue(req["url"].endswith("/v1/text-to-speech/VOICE123"))
        self.assertEqual(req["json"]["model_id"], "eleven_multilingual_v2")
        self.assertEqual(req["json"]["voice_settings"], {"stability": 0.5})

    def test_engine_module_has_no_network_code(self):
        import factory.voice_studio.engines.elevenlabs as el
        source = Path(el.__file__).read_text()
        for word in ("urllib", "requests", "http.client", "socket"):
            self.assertNotIn(f"import {word}", source)
        self.assertNotIn("requests", sys.modules.get(el.__name__).__dict__)


class TestVoiceCloning(Base):
    def sign(self, data, signature=None):
        path = clones.clone_dir(self.ctx, data["name"]) / "consent.md"
        text = path.read_text().replace("- [ ]", "- [x]").replace("Signed:", f"Signed: {signature or data['owner']}")
        path.write_text(text)

    def test_full_consent_flow_and_use(self):
        data = clones.init_clone(self.ctx, "My Voice", "Aisha Rahman")
        self.assertEqual((data["name"], data["status"]), ("my-voice", "awaiting_consent"))
        consent = (clones.clone_dir(self.ctx, "my-voice") / "consent.md").read_text()
        self.assertIn(data["verification_phrase"], consent)
        phrase_rec = make_wav(self.tmp / "phrase.wav", 2)

        with self.assertRaises(FactoryError):          # consent not signed
            clones.verify_clone(self.ctx, "my-voice", phrase_rec)
        self.sign(data)
        clones.verify_clone(self.ctx, "my-voice", phrase_rec)

        with self.assertRaises(FactoryError):          # no samples yet
            clones.create_clone(self.ctx, "my-voice", get_engine(self.ctx, "mock"), YES)
        clones.add_sample(self.ctx, "my-voice", make_wav(self.tmp / "sample.wav", 3))
        with self.assertRaises(FactoryError):          # clone not ready → can't be used
            service.text_to_speech(self.ctx, self.p, voice="clone:my-voice")
        ready = clones.create_clone(self.ctx, "my-voice", get_engine(self.ctx, "mock"), YES)
        self.assertEqual(ready["status"], "ready")
        self.assertTrue(ready["engine_voice_ids"]["mock"].startswith("mock-clone-"))

        item = service.text_to_speech(self.ctx, self.p, voice="clone:my-voice")
        self.assertEqual(item["voice"], "clone:my-voice")
        with self.assertRaises(FactoryError):          # not created on this engine
            service.text_to_speech(self.ctx, self.p, voice="clone:my-voice", engine_name="elevenlabs", confirm=YES)

    def test_wrong_signature_rejected(self):
        data = clones.init_clone(self.ctx, "v", "Aisha Rahman")
        self.sign(data, signature="Someone Else")
        with self.assertRaises(FactoryError) as e:
            clones.verify_clone(self.ctx, "v", make_wav(self.tmp / "p.wav"))
        self.assertIn("Signature", str(e.exception))

    def test_consent_tampering_blocks_use(self):
        data = clones.init_clone(self.ctx, "v", "Aisha Rahman")
        self.sign(data)
        clones.verify_clone(self.ctx, "v", make_wav(self.tmp / "p.wav"))
        clones.add_sample(self.ctx, "v", make_wav(self.tmp / "s.wav"))
        clones.create_clone(self.ctx, "v", get_engine(self.ctx, "mock"), YES)
        path = clones.clone_dir(self.ctx, "v") / "consent.md"
        path.write_text(path.read_text() + "\nedited later")
        with self.assertRaises(FactoryError) as e:
            service.text_to_speech(self.ctx, self.p, voice="clone:v")
        self.assertIn("changed after verification", str(e.exception))

    def test_upload_of_samples_needs_confirmation(self):
        data = clones.init_clone(self.ctx, "v", "Aisha Rahman")
        self.sign(data)
        clones.verify_clone(self.ctx, "v", make_wav(self.tmp / "p.wav"))
        clones.add_sample(self.ctx, "v", make_wav(self.tmp / "s.wav"))
        with self.assertRaises(FactoryError) as e:
            clones.create_clone(self.ctx, "v", get_engine(self.ctx, "elevenlabs"), NO)
        self.assertIn("nothing was uploaded", str(e.exception))
        self.assertEqual(clones.load_clone(self.ctx, "v")["status"], "verified")

    @unittest.skipUnless(os.name == "posix", "POSIX permissions")
    def test_clone_metadata_private(self):
        clones.init_clone(self.ctx, "v", "Aisha Rahman")
        mode = (clones.clone_dir(self.ctx, "v") / "voice.json").stat().st_mode
        self.assertEqual(mode & 0o077, 0)

    def test_delete(self):
        clones.init_clone(self.ctx, "v", "Aisha Rahman")
        clones.delete_clone(self.ctx, "v")
        self.assertEqual(clones.list_clones(self.ctx), [])


if __name__ == "__main__":
    unittest.main()
