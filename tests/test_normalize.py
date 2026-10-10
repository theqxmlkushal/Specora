"""Unit normalisation: pressure, temperature, length, gauge/absolute, decimal comma."""
from engine.ingest import parse_value_unit, parse_value_unit_full
from engine.normalize import (amb_issue_from, normalize_length, normalize_pressure,
                              normalize_temperature, parse_number)


def test_psi_to_mpa():
    v, u, notes, iss = normalize_pressure(145, "psig")
    assert u == "MPa(g)" and abs(v - 1.0) < 0.005 and iss is None
    assert any("145 psig" in n for n in notes)


def test_bar_conversions():
    assert abs(normalize_pressure(8, "barg")[0] - 0.8) < 1e-9
    assert abs(normalize_pressure(80, "bar(g)")[0] - 8.0) < 1e-9
    assert abs(normalize_pressure(1000, "kPag")[0] - 1.0) < 1e-9


def test_gauge_vs_absolute():
    v, _, notes, _ = normalize_pressure(11.0, "bara")
    assert abs(v - (1.1 - 0.101325)) < 1e-6          # -> gauge
    assert any("gauge" in n for n in notes)
    v2, _, _, iss = normalize_pressure(145, "psia")
    assert abs(v2 - (145 * 0.006894757 - 0.101325)) < 1e-6


def test_unitless_pressure_is_ambiguous_red():
    v, _, _, iss = normalize_pressure(8, "")
    assert v is None and iss is not None
    assert iss.code == "UNIT_AMBIGUOUS" and iss.severity == "RED"
    assert iss.question


def test_bare_bar_is_flagged():
    v, _, _, iss = normalize_pressure(8, "bar")
    assert abs(v - 0.8) < 1e-9                       # provisional
    assert iss is not None and iss.code == "UNIT_AMBIGUOUS" and iss.severity == "AMBER"


def test_temperature_conversions():
    assert abs(normalize_temperature(212, "degF")[0] - 100) < 1e-6
    assert abs(normalize_temperature(60, "degC")[0] - 60) < 1e-9
    assert abs(normalize_temperature(300, "K")[0] - 26.85) < 1e-6
    assert normalize_temperature(50, "")[0] is None


def test_length_conversions():
    assert abs(normalize_length(48, "in")[0] - 1219.2) < 1e-6
    assert abs(normalize_length(2, "m")[0] - 2000) < 1e-9
    assert abs(normalize_length(10, "cm")[0] - 100) < 1e-9


def test_decimal_comma_and_thousands():
    assert parse_number("1,5")[0] == 1.5
    assert parse_number("1,5")[2] == "UNIT_AMBIGUOUS"
    assert parse_number("1,200")[0] == 1200
    assert parse_number("1,200")[2] == "UNIT_AMBIGUOUS"
    assert parse_number("1.200")[0] == 1.2
    assert parse_number("  60 ")[0] == 60


def test_value_unit_split():
    assert parse_value_unit("145 psig") == (145.0, "psig")
    assert parse_value_unit("8.0 bar(g)")[1] == "bar(g)"
    assert parse_value_unit("SA-516-70")[0] is None
    assert parse_value_unit("spot") == (None, "spot")
    assert parse_value_unit("1,200")[0] == 1200
    num, unit, notes, amb = parse_value_unit_full("1,200 mm")
    assert num == 1200 and unit == "mm" and amb == "UNIT_AMBIGUOUS"


def test_amb_issue_shape():
    i = amb_issue_from("UNIT_AMBIGUOUS", "inside_diameter", "Sheet1!B4")
    assert i.code == "UNIT_AMBIGUOUS" and i.severity == "AMBER" and i.locators
