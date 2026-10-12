import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import enrich as e


class Fake(e.Provider):
    def __init__(self, name, emails=None, phones=None, verifier=None, fatal=False):
        self.name, self.key, self.calls = name, "x", 0
        self.kinds = ("email", "phone", "verify")
        self.credits = {"email": 1, "phone": 10, "verify": 1}
        self.emails, self.phones, self.vmap, self.fatal = emails or {}, phones or {}, verifier or {}, fatal

    def find_email(self, p):
        self.calls += 1
        if self.fatal:
            raise e.FatalProviderError("no credits")
        v = self.emails.get(p["full_name"])
        return (v[0], {"verified_by_provider": v[1]}) if v else None

    def find_phone(self, p):
        self.calls += 1
        v = self.phones.get(p["full_name"])
        return (v, {"line_type": "mobile"}) if v else None

    def verify(self, email):
        return self.vmap.get(email, "valid")


def engine(mock, email=("a", "b"), phone=("a",), max_credits=None):
    cfg = {"email": list(email), "phone": list(phone), "verifier": "v"}
    return e.Engine(cfg, e.Cache(":none:"), max_credits, mock)


REC = {"id": "003X", "First Name": "Ada", "Last Name": "Lovelace", "Website": "https://www.acme.com/about"}


class T(unittest.TestCase):
    def test_normalize(self):
        p = e.normalize(REC)
        self.assertEqual((p["full_name"], p["domain"]), ("Ada Lovelace", "acme.com"))
        self.assertFalse(e.can_match(e.normalize({"name": "Ada"})))
        self.assertTrue(e.can_match(e.normalize({"linkedin_url": "https://linkedin.com/in/ada"})))

    def test_fallback_to_second_provider_and_passthrough(self):
        a, b = Fake("a"), Fake("b", emails={"Ada Lovelace": ("ada@acme.com", True)})
        out = engine({"a": a, "b": b, "v": Fake("v")}).enrich(REC)
        self.assertEqual((out["email_found"], out["email_source"], out["email_status"]), ("ada@acme.com", "b", "valid"))
        self.assertEqual(out["id"], "003X")
        self.assertIn("a:miss > b:hit", out["enrich_trace"])

    def test_invalid_email_falls_through(self):
        a = Fake("a", emails={"Ada Lovelace": ("bad@acme.com", False)})
        b = Fake("b", emails={"Ada Lovelace": ("ada@acme.com", True)})
        v = Fake("v", verifier={"bad@acme.com": "invalid"})
        out = engine({"a": a, "b": b, "v": v}).enrich(REC)
        self.assertEqual(out["email_found"], "ada@acme.com")

    def test_risky_kept_only_as_last_resort(self):
        a = Fake("a", emails={"Ada Lovelace": ("r@acme.com", False)})
        v = Fake("v", verifier={"r@acme.com": "risky"})
        out = engine({"a": a, "b": Fake("b"), "v": v}).enrich(REC)
        self.assertEqual((out["email_found"], out["email_status"]), ("r@acme.com", "risky"))

    def test_fatal_disables_provider_for_run(self):
        a, b = Fake("a", fatal=True), Fake("b", emails={"Ada Lovelace": ("ada@acme.com", True)})
        eng = engine({"a": a, "b": b, "v": Fake("v")})
        eng.enrich(REC); eng.enrich(REC)
        self.assertEqual(a.calls, 1)
        self.assertIn("a", eng.dead)

    def test_phone_and_credit_cap(self):
        a = Fake("a", phones={"Ada Lovelace": "+4915112345678"})
        eng = engine({"a": a, "b": Fake("b"), "v": Fake("v")})
        out = eng.enrich(REC, want_email=False, want_phone=True)
        self.assertEqual(out["phone_found"], "+4915112345678")
        capped = engine({"a": Fake("a", phones={"Ada Lovelace": "+1"}), "b": Fake("b"), "v": Fake("v")}, max_credits=5)
        out = capped.enrich(REC, want_email=False, want_phone=True)
        self.assertEqual(out["phone_found"], "")

    def test_existing_email_verified_and_replaced_when_invalid(self):
        b = Fake("b", emails={"Ada Lovelace": ("ada@acme.com", True)})
        v = Fake("v", verifier={"old@acme.com": "invalid"})
        out = engine({"a": Fake("a"), "b": b, "v": v}).enrich(dict(REC, email="old@acme.com"))
        self.assertEqual((out["email_found"], out["email_source"]), ("ada@acme.com", "b"))

    def test_unmatchable_record_skipped_without_calls(self):
        a = Fake("a")
        out = engine({"a": a, "b": Fake("b"), "v": Fake("v")}).enrich({"name": "Ada"})
        self.assertEqual(a.calls, 0)
        self.assertTrue(out["enrich_trace"].startswith("skipped"))

    def test_cache_prevents_second_charge(self):
        a = Fake("a", emails={"Ada Lovelace": ("ada@acme.com", True)})
        eng = e.Engine({"email": ["a"], "phone": [], "verifier": "v"}, e.Cache("/tmp/_enrich_test.sqlite"), None, {"a": a, "v": Fake("v")})
        try:
            eng.enrich(REC); eng.enrich(REC)
            self.assertEqual(a.calls, 1)
        finally:
            os.remove("/tmp/_enrich_test.sqlite")


if __name__ == "__main__":
    unittest.main()
