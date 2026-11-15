"""Known-answer tests for landslide geology classification.

Labels and pixel counts are hand-written. They are not observations.
"""

from gee_math.landslide_geology import (
    classes_present,
    dominant_unit,
    engineering_class,
    structure_summary,
)


def test_engineering_class_matches_stems_and_leaves_unknown_unclassified():
    assert engineering_class("Depósito coluvial") == "colluvium"
    assert engineering_class("Arenisca de la Formación Amagá") == "rock"
    assert engineering_class("Arcilla aluvial") == "soil"
    assert engineering_class("unidad sin nombre publicado") is None
    assert engineering_class(None) is None
    assert engineering_class("  ") is None


def test_dominant_unit_uses_the_largest_count_and_skips_missing_counts():
    units = [
        {"name": "B", "lithology": "arcilla", "pixel_count": 5},
        {"name": "A", "lithology": "arenisca", "pixel_count": 5},
        {"name": "C", "lithology": "coluvión", "pixel_count": None},
        {"name": "D", "lithology": "gneis", "pixel_count": 9},
    ]
    dominant = dominant_unit(units)
    assert dominant["name"] == "D"
    assert dominant["engineering_class"] == "rock"
    assert dominant["pixel_count"] == 9
    assert dominant["n_units_with_count"] == 3
    assert dominant["n_units_missing_count"] == 1
    tied = [
        {"name": "B", "lithology": "arcilla", "pixel_count": 5},
        {"name": "A", "lithology": "arcilla", "pixel_count": 5},
    ]
    assert dominant_unit(tied)["name"] == "A"
    assert dominant_unit([{"name": "X", "lithology": "arcilla", "pixel_count": None}]) is None
    assert classes_present(units) == ["colluvium", "rock", "soil"]


def test_structure_summary_does_not_treat_a_missing_flag_as_no_intersection():
    summary = structure_summary(
        [
            {"kind": "fault", "name": "Falla Norte", "intersects": True},
            {"kind": "contact", "name": "Contacto Sur", "intersects": False},
            {"kind": "fault", "name": "Falla sin corte", "intersects": None},
        ]
    )
    assert summary["faults_intersecting"] == 1
    assert summary["contacts_intersecting"] == 0
    assert summary["n_missing_intersection"] == 1
    assert summary["intersecting_names"] == ["Falla Norte"]
