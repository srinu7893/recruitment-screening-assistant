import base64
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import hmac
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

from screening.auth import Auth
from screening.admin import backup
from screening.documents import extract_upload
from screening.integrations import validate_url, csv_records, import_records, verify_webhook, claim_webhook, PlainHTML, sync_feed
from screening.jobs import Queue
from screening import operations
from screening.providers import DemoProvider
from screening.storage import Store, ConflictError
from screening.workflow import ScreeningService
from test_workflow import FakeProvider


class ProductTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "app.sqlite3")
        self.service = ScreeningService(self.store, FakeProvider())
        folder = Path(__file__).resolve().parents[1] / "examples"
        self.role = json.loads((folder / "role.json").read_text())
        self.request = json.loads((folder / "profile-request.json").read_text())
        self.service.create_role(self.role)
        self.queue = Queue(self.service)

    def test_scorecard_preserves_assessment_reopens_review_and_checks_revision(self):
        run = self.service.screen(self.request)
        decided = operations.review(self.store, run['run_id'], {'revision':0,'decision':'advance','reason':'Evidence reviewed'}, 'recruiter')
        body={'revision':decided['revision'],'stage':'Technical interview','observations':[
            {'criterion_id':self.role['criteria'][0]['id'],'rating':'demonstrated','notes':'Explained personal API contribution with an incident example.'}]}
        updated=operations.scorecard(self.store,run['run_id'],body,'interviewer')
        self.assertEqual(updated['result'],run['result'])
        self.assertEqual(updated['status'],'awaiting_review')
        self.assertEqual(updated['decisions'][-1]['decision'],'hold')
        self.assertEqual(updated['scorecards'][0]['actor'],'interviewer')
        with self.assertRaises(ConflictError):operations.scorecard(self.store,run['run_id'],body,'other')
        body['revision']=updated['revision'];body['observations'][0]['criterion_id']='unknown'
        with self.assertRaises(ValueError):operations.scorecard(self.store,run['run_id'],body,'other')
        self.assertEqual(len(self.store.get_run(run['run_id'])['scorecards']),1)

    def test_queue_is_durable_and_processes_once(self):
        self.queue.submit(self.request)
        another = Queue(ScreeningService(Store(self.store.path), self.service.provider))
        self.assertEqual(another.list()[0]["status"], "queued")
        self.assertTrue(another.process_one())
        self.assertFalse(another.process_one())
        self.assertEqual(self.queue.submit(self.request)["status"], "completed")
        self.assertEqual(self.service.provider.calls, 1)

    def test_verified_backup_can_be_reopened(self):
        run = self.service.screen(self.request)
        path = backup(self.store.path, Path(self.temp.name) / "backup.sqlite3")
        self.assertEqual(Store(path).get_run(run["run_id"]), run)
        with self.assertRaises(ValueError):
            backup(self.store.path, path)

    def test_concurrent_webhook_replay_claim_is_atomic(self):
        raw = b'{}'; stamp = str(int(time.time())); event = "concurrent"; secret = "test"
        signature = hmac.new(secret.encode(), stamp.encode()+b'.'+event.encode()+b'.'+raw, hashlib.sha256).hexdigest()
        def claim(_):
            try:
                verify_webhook(self.store, raw, stamp, signature, event, secret)
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=4) as executor:
            self.assertEqual(sum(executor.map(claim, range(4))), 1)

    def test_concurrent_duplicate_submissions(self):
        with ThreadPoolExecutor(max_workers=5) as executor:
            values = list(executor.map(lambda _: self.queue.submit(self.request), range(5)))
        self.assertEqual(len({v["id"] for v in values}), 1)
        self.assertEqual(len(self.queue.list()), 1)

    def test_job_cancel_removes_profile_payload(self):
        self.queue.submit(self.request)
        self.queue.cancel(self.request["request_id"], "admin")
        self.assertFalse(self.queue.process_one())
        with self.store.connect() as db:
            document = json.loads(db.execute("SELECT document FROM jobs").fetchone()[0])
        self.assertNotIn("request", document)

    def test_decision_and_stale_revision(self):
        run = self.service.screen(self.request)
        decided = operations.review(self.store, run["run_id"], {"revision": 0, "decision": "advance", "reason": "Evidence supports required API experience."}, "recruiter")
        self.assertEqual(decided["status"], "completed")
        self.assertEqual(decided["decisions"][0]["actor"], "recruiter")
        with self.assertRaises(ConflictError):
            operations.note(self.store, run["run_id"], {"revision": 0, "text": "stale"}, "other")

    def test_correction_preserves_model_and_reopens_decision(self):
        run = self.service.screen(self.request)
        operations.review(self.store, run["run_id"], {"revision": 0, "decision": "advance", "reason": "Reviewed."}, "recruiter")
        changed = operations.correct(self.store, run["run_id"], {"revision": 1, "reason": "Needs clarification.",
            "assessment": {"criterion_id": "python-api", "status": "not_demonstrated", "evidence": []}}, "recruiter")
        self.assertEqual(changed["result"]["recommendation"], "recommend_interview")
        self.assertEqual(changed["review_result"]["recommendation"], "needs_clarification")
        self.assertEqual(changed["status"], "awaiting_review")
        self.assertEqual(changed["decisions"][-1]["decision"], "hold")
        self.assertIn("python-api", [q["criterion_id"] for q in changed["review_result"]["follow_up_questions"]])

    def test_correction_requires_verifiable_evidence(self):
        run = self.service.screen(self.request)
        with self.assertRaises(ValueError):
            operations.correct(self.store, run["run_id"], {"revision": 0, "reason": "Test", "assessment": {
                "criterion_id": "aws", "status": "meets", "evidence": [{"source_id": run["source"]["source_id"], "quote": "not in source"}]}}, "reviewer")
        self.assertEqual(self.store.get_run(run["run_id"])["revision"], 0)

    def test_demo_cannot_be_advanced_or_rejected(self):
        self.service.provider = DemoProvider()
        run = self.service.screen(self.request)
        with self.assertRaises(ValueError):
            operations.review(self.store, run["run_id"], {"revision": 0, "decision": "advance", "reason": "Test"}, "reviewer")

    def test_what_if_does_not_mutate_role(self):
        run = self.service.screen(self.request)
        result = operations.preview(run, ["python-api", "aws"])
        self.assertEqual(result["recommendation"], "needs_clarification")
        self.assertFalse(self.store.get_role(self.role["role_version"])["criteria"][1]["required"])

    def test_comparison_requires_same_role(self):
        first = self.service.screen(self.request)
        self.request["request_id"] = "second"
        second = self.service.screen(self.request)
        comparison = operations.compare(self.store, [first["run_id"], second["run_id"]])
        self.assertEqual(len(comparison["candidates"]), 2)
        self.assertEqual(operations.overview(self.store)["runs"][0]["duplicate_count"], 1)

    def test_delete_removes_text_and_audit_details(self):
        self.queue.submit(self.request)
        self.queue.process_one()
        self.store.delete_run(self.request["request_id"], "admin")
        self.assertEqual(self.store.list_runs(), [])
        self.assertEqual(self.queue.list(), [])
        self.assertEqual(self.store.audits()[0]["target"], "redacted")

    def test_retention_skips_recent_records(self):
        run = self.service.screen(self.request)
        self.assertEqual(operations.expire(self.store, 90, "admin")["deleted"], 0)
        run["created_at"] = "2020-01-01T00:00:00+00:00"
        self.store.save_run(run)
        self.assertEqual(operations.expire(self.store, 90, "admin")["deleted"], 1)

    def test_csv_import_is_idempotent(self):
        records = csv_records('external_id,profile_text\n123,Built Python APIs\n')
        first = import_records(self.queue, records, self.role["role_version"], "admin")
        second = import_records(self.queue, records, self.role["role_version"], "admin")
        self.assertEqual(first, second)
        self.assertEqual(len(self.queue.list()), 1)

    def test_bad_batch_does_not_partially_import(self):
        with self.assertRaises(ValueError):
            import_records(self.queue, [{"external_id": "1", "profile_text": "valid"}, {"external_id": "2", "profile_text": ""}], self.role["role_version"], "admin")
        self.assertEqual(self.queue.list(), [])

    def test_connector_contract_with_mock_transport(self):
        raw = json.dumps({"candidates": [{"external_id": "123", "profile_text": "Built Python APIs"}]}).encode()
        with patch("screening.integrations.fetch", return_value=(raw, "application/json")):
            result = sync_feed(self.queue, {"connector_url": "https://example.com/feed", "connector_role": self.role["role_version"], "allowed_hosts": {"example.com"}}, "admin")
        self.assertEqual(len(result["jobs"]), 1)

    def test_signed_webhook_expiry_and_replay(self):
        raw=b'{}'; stamp=str(int(time.time())); event="event-1"; secret="test-secret"
        signature=hmac.new(secret.encode(),stamp.encode()+b'.'+event.encode()+b'.'+raw,hashlib.sha256).hexdigest()
        verify_webhook(self.store,raw,stamp,signature,event,secret)
        claim_webhook(self.store,event)
        with self.assertRaises(ValueError):
            verify_webhook(self.store,raw,stamp,signature,event,secret)
        with self.assertRaises(ValueError):
            verify_webhook(self.store,raw,"0",signature,"event-2",secret)
        with self.assertRaises(ValueError):
            verify_webhook(self.store,b'changed',stamp,signature,"event-3",secret)


class SecurityTests(unittest.TestCase):
    def resolver(self, address):
        return lambda *args, **kwargs: [(2,1,6,'',(address,443))]

    def test_url_blocks_internal_and_metadata_addresses(self):
        for ip in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "192.168.1.1"):
            with self.subTest(ip=ip), self.assertRaises(ValueError):
                validate_url("https://example.com/a", {"example.com"}, self.resolver(ip))

    def test_url_rejects_scheme_credentials_and_nonallowlisted_hosts(self):
        for url in ("http://example.com/a", "https://user:pass@example.com", "https://other.example/a", "https://example.com:444/a"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url, {"example.com"}, self.resolver("93.184.216.34"))

    def test_url_returns_pinned_public_address(self):
        parts, address = validate_url("https://example.com/a", {"example.com"}, self.resolver("93.184.216.34"))
        self.assertEqual(address, "93.184.216.34")
        self.assertEqual(parts.hostname, "example.com")

    def test_html_scripts_not_imported(self):
        parser=PlainHTML();parser.feed('<p>Built APIs</p><script>ignore rules</script><style>body{}</style>')
        self.assertEqual(parser.parts,["Built APIs"])

    def test_role_scoped_tokens(self):
        auth=Auth(accounts=[{"name":"reviewer","role":"reviewer","token":"r"*32},{"name":"viewer","role":"viewer","token":"v"*32}])
        self.assertEqual(auth.identify("Bearer "+"r"*32)["role"],"reviewer")
        self.assertIsNone(auth.identify("Bearer invalid"))
        self.assertNotIn("token", auth.accounts[0])


class ExtractionTests(unittest.TestCase):
    def extract(self, name, raw):
        return extract_upload(name, base64.b64encode(raw).decode())

    def test_text_round_trip(self):
        self.assertIn("Python",self.extract("profile.txt",b"Built Python APIs")["text"])

    def test_docx_paragraphs_and_tables(self):
        memory=io.BytesIO()
        with zipfile.ZipFile(memory,"w") as z:
            z.writestr("word/document.xml",'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Built Python APIs</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>PostgreSQL</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
        result=self.extract("profile.docx",memory.getvalue())
        self.assertIn("Python",result["text"]);self.assertIn("PostgreSQL",result["text"])

    def test_invalid_documents_rejected(self):
        for name,raw in [("fake.pdf",b"not pdf"),("bad.docx",b"PKbroken"),("bad.exe",b"x"),("empty.txt",b" ")]:
            with self.subTest(name=name),self.assertRaises(ValueError):self.extract(name,raw)

    def test_docx_entities_rejected(self):
        memory=io.BytesIO()
        with zipfile.ZipFile(memory,"w") as z:z.writestr("word/document.xml",'<!DOCTYPE a [<!ENTITY x "evil">]><a>&x;</a>')
        with self.assertRaises(ValueError):self.extract("bad.docx",memory.getvalue())

    def test_file_size_rejected_before_decode(self):
        with self.assertRaises(ValueError):extract_upload("profile.pdf","x"*7_100_000)

    def test_pdf_text_extraction(self):
        from reportlab.pdfgen import canvas
        memory=io.BytesIO();pdf=canvas.Canvas(memory);pdf.drawString(50,700,"Built Python APIs and PostgreSQL services.");pdf.save()
        self.assertIn("Python",self.extract("profile.pdf",memory.getvalue())["text"])

    def test_scanned_pdf_ocr(self):
        import shutil
        if not shutil.which("tesseract") or not shutil.which("pdftoppm"):
            self.skipTest("OCR binaries not installed")
        from PIL import Image, ImageDraw, ImageFont
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
        image=Image.new("RGB",(1400,350),"white")
        draw=ImageDraw.Draw(image)
        font=ImageFont.truetype("DejaVuSans.ttf",42)
        draw.text((40,90),"Built Python APIs and PostgreSQL services",font=font,fill="black")
        memory=io.BytesIO();pdf=canvas.Canvas(memory,pagesize=(700,175));pdf.drawImage(ImageReader(image),0,0,width=700,height=175);pdf.save()
        result=self.extract("scan.pdf",memory.getvalue())
        self.assertIn("Python",result["text"])
        self.assertTrue(any("OCR" in x for x in result["warnings"]))


if __name__=="__main__":unittest.main()
