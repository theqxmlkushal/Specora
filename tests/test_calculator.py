"""Golden case from the build spec (section 5)."""
import yaml

from engine import calculator as calc

RULES = yaml.safe_load(open("rules/vessel_rules.yaml", encoding="utf-8"))
MATS = yaml.safe_load(open("rules/materials.yaml", encoding="utf-8"))


def test_golden_case():
    P_op, ID, S, E, CA = 8 / 10, 1200, 138, 0.85, 3      # 8 bar(g) -> 0.8 MPa(g)
    P_design = calc.design_pressure_mpa_g(P_op, RULES)
    assert abs(P_design - 1.0) < 1e-9                       # max(0.88, 1.0)
    t_req, t_ca = calc.shell_min_thickness_mm(P_design, ID / 2, S, E, CA)   # R = 600 + 3 = 603
    assert abs(t_req - 5.167) < 0.01                        # ~5.17 mm
    assert abs(t_ca - 8.167) < 0.01                         # ~8.17 mm
    assert calc.select_standard_thickness(t_ca, RULES["thickness_ladder_mm"]) == 10
    ht = calc.hydrotest_mpa_g(P_design, 1.3, 1.0)
    assert abs(ht - 1.3) < 1e-9                             # 1.3 MPa(g) = 13 bar(g)
    assert abs(ht * 10 - 13) < 1e-9


def test_design_pressure_margin_rule():
    # margin 10% vs +2 bar floor — whichever is bigger
    assert abs(calc.design_pressure_mpa_g(0.5, RULES) - 0.7) < 1e-9     # +2 bar wins
    assert abs(calc.design_pressure_mpa_g(0.8, RULES) - 1.0) < 1e-9     # +2 bar wins
    assert abs(calc.design_pressure_mpa_g(3.0, RULES) - 3.3) < 1e-9     # 10% wins


def test_thin_wall_validity_guard():
    try:
        calc.shell_min_thickness_mm(60.0, 600, 138, 0.85, 3)
        raise AssertionError("should have raised")
    except ValueError:
        pass


def test_material_selection_sour_and_default():
    g, i, _ = calc.select_material("sweet gas", None, None, MATS)
    assert g == "SA-516-70" and i == 3
    g, i, _ = calc.select_material("sour condensate", 150, None, MATS)
    assert g == "SA-516-70N-HIC" and i == 0
    g, i, _ = calc.select_material("seawater", None, None, MATS)
    assert g == "SA-240-316L" and i == 1
    g, i, _ = calc.select_material("sweet gas", None, -40, MATS)
    assert g == "SA-516-70N-HIC" and i == 2


def test_pwht_rules():
    assert calc.pwht_required(10, True, RULES) is True     # sour service
    assert calc.pwht_required(40, False, RULES) is True     # thick shell
    assert calc.pwht_required(10, False, RULES) is False


def test_joint_efficiency():
    assert calc.joint_efficiency("full", RULES) == 1.0
    assert calc.joint_efficiency("spot", RULES) == 0.85
    assert calc.joint_efficiency("none", RULES) == 0.70
    assert calc.joint_efficiency(None, RULES) == 0.70
