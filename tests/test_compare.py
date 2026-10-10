"""Comparator operators, vague/missing handling and TBE scoring."""
from engine.compare import compare_one, is_vague
from engine.tbe import robustness, score, what_if
from models import ReqResult


def _req(**kw):
    base = dict(id="R01", key="design_pressure", op=">=", category="Design basis",
                critical=True, weight=3, source="MDS")
    base.update(kw)
    return base


class FakeCand:
    def __init__(self, raw_value, raw_unit="", locator="Offer!C2"):
        self.raw_value = raw_value
        self.raw_unit = raw_unit
        self.locator = locator
        self.source_file = "Vendor.xlsx"


def test_numeric_greater_equal():
    r = compare_one(_req(), 1.0, "MPa(g)", "1 MPa(g)", "Vendor A", FakeCand(12, "barg"), None)
    assert r.verdict == "Compliant" and "exceeds" in r.explanation.lower()
    r2 = compare_one(_req(), 1.0, "MPa(g)", "1 MPa(g)", "Vendor B", FakeCand(5, "barg"), None)
    assert r2.verdict == "Deviating"


def test_text_equals():
    req = _req(key="shell_material", op="==", id="R03")
    assert compare_one(req, "SA-516-70", "", "SA-516-70", "A",
                       FakeCand("SA-516-70"), None).verdict == "Compliant"
    assert compare_one(req, "SA-516-70", "", "SA-516-70", "B",
                       FakeCand("SA-516-60"), None).verdict == "Deviating"


def test_order_operator():
    req = _req(key="radiography", op=">=", id="R06", order=["none", "spot", "full"])
    assert compare_one(req, "spot", "", "spot", "A", FakeCand("full"), None).verdict == "Compliant"
    assert compare_one(req, "spot", "", "spot", "B", FakeCand("none"), None).verdict == "Deviating"


def test_contains_operator():
    req = _req(key="certificates", op="contains", value="EN 10204 3.1",
               id="R10", source="ENQUIRY", critical=False)
    r = compare_one(req, "EN 10204 3.1", "", "EN 10204 3.1", "A",
                    FakeCand("EN 10204 3.1"), None)
    assert r.verdict == "Compliant"


def test_missing_and_unclear():
    req = _req(id="R07", key="hydrotest_pressure")
    r = compare_one(req, 1.3, "MPa(g)", "1.3 MPa(g)", "Vendor C", None, None)
    assert r.verdict == "Missing" and r.question and "Vendor C" in r.question
    r2 = compare_one(req, 1.3, "MPa(g)", "1.3 MPa(g)", "Vendor C",
                     FakeCand("as per standard"), None)
    assert r2.verdict == "Unclear"


def test_vague_detection():
    assert is_vague("as per standard") and is_vague("TBC") and is_vague("per code")
    assert not is_vague("SA-516-70") and not is_vague("10 mm")


def _results():
    mk = lambda v, rid, verdict, cat, crit, w: ReqResult(
        req_id=rid, vendor=v, required="x", offered="y", verdict=verdict,
        critical=crit, category=cat, explanation="", weight=w, key=rid, op=">=")
    out = []
    out += [mk("A", "R01", "Compliant", "Design basis", True, 3),
            mk("A", "R02", "Compliant", "Design basis", False, 2),
            mk("B", "R01", "Compliant", "Design basis", True, 3),
            mk("B", "R02", "Deviating", "Design basis", True, 2)]
    return out


def test_scoring_and_ranking():
    s = score(_results())
    assert s["vendors"]["A"]["total"] > s["vendors"]["B"]["total"]
    assert s["vendors"]["B"]["acceptable"] is False          # critical deviation
    assert s["ranking"][0] == "A"


def test_what_if_and_robustness():
    from models import ReqResult as R
    rs = [R(req_id="R01", vendor="A", required="x", offered="y", verdict="Missing",
            critical=True, category="Design basis", explanation="", weight=3,
            key="R01", op=">="),
          R(req_id="R01", vendor="B", required="x", offered="y", verdict="Compliant",
            critical=True, category="Design basis", explanation="", weight=3,
            key="R01", op=">=")]
    base = score(rs)
    assert base["ranking"][0] == "B"
    wi = what_if(rs)
    assert wi["vendors"]["A"]["total"] >= base["vendors"]["A"]["total"]
    rob = robustness(rs, trials=50, seed=1)
    assert abs(sum(rob["pct"].values()) - 100) < 3.0
