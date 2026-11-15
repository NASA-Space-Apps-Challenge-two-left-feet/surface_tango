"""Conditioning lithology for a landslide AOI.

The functions classify a lithology label that a public geology layer already
supplied and pick the dominant unit by a staged pixel count. They do not invent
a unit, a contact, or a count. An unrecognized label stays unclassified.
"""

from __future__ import annotations

import math

# Stems are matched in this order. "arenisca" must beat the soil stem "arena".
_COLLUVIUM = ("coluvi", "colluv", "talus")
_ROCK = (
    "arenisca",
    "gneis",
    "granit",
    "basalt",
    "andesit",
    "caliza",
    "lutita",
    "esquisto",
    "anfibolit",
    "dunita",
    "diorit",
    "gabro",
    "diabasa",
    "batolit",
    "roca",
    "rock",
)
_SOIL = ("suelo", "soil", "aluv", "arcilla", "limo", "arena", "saprol", "relleno", "fill")


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def engineering_class(lithology: object) -> str | None:
    """Map one staged lithology label to rock, soil, or colluvium.

    Returns None when the label is missing or matches none of the stems.
    """
    if _blank(lithology) or not isinstance(lithology, str):
        return None
    text = lithology.casefold()
    if any(stem in text for stem in _COLLUVIUM):
        return "colluvium"
    if any(stem in text for stem in _ROCK):
        return "rock"
    if any(stem in text for stem in _SOIL):
        return "soil"
    return None


def dominant_unit(units: list[dict]) -> dict | None:
    """Unit with the largest finite pixel count. Ties break toward the smaller name.

    A unit with a missing count is excluded. If every count is missing, the
    result is None rather than an arbitrary pick.
    """
    ranked: list[tuple[float, str, dict]] = []
    missing = 0
    for unit in units:
        if not isinstance(unit, dict):
            missing += 1
            continue
        count = _finite_number(unit.get("pixel_count"))
        if count is None or count < 0:
            missing += 1
            continue
        name = unit.get("name")
        label = name if isinstance(name, str) else ""
        ranked.append((count, label, unit))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], item[1]))
    count, _name, best = ranked[0]
    lithology = best.get("lithology")
    return {
        "name": best.get("name") if isinstance(best.get("name"), str) else None,
        "lithology": lithology if isinstance(lithology, str) else None,
        "engineering_class": engineering_class(lithology),
        "pixel_count": count,
        "n_units_with_count": len(ranked),
        "n_units_missing_count": missing,
    }


def structure_summary(structures: list[dict]) -> dict:
    """Count faults and contacts whose staged intersection flag is true.

    A missing flag is counted as missing and is not treated as "does not intersect".
    """
    faults = 0
    contacts = 0
    missing = 0
    names: list[str] = []
    for item in structures:
        if not isinstance(item, dict):
            missing += 1
            continue
        flag = item.get("intersects")
        if flag is None:
            missing += 1
            continue
        if flag is not True and flag is not False:
            missing += 1
            continue
        if flag is False:
            continue
        kind = item.get("kind")
        kind_text = kind.casefold() if isinstance(kind, str) else ""
        if kind_text == "fault":
            faults += 1
        elif kind_text == "contact":
            contacts += 1
        else:
            missing += 1
            continue
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name)
    return {
        "faults_intersecting": faults,
        "contacts_intersecting": contacts,
        "n_missing_intersection": missing,
        "intersecting_names": names,
    }


def classes_present(units: list[dict]) -> list[str]:
    """Sorted engineering classes that at least one labeled unit actually matches."""
    found: set[str] = set()
    for unit in units:
        if not isinstance(unit, dict):
            continue
        label = engineering_class(unit.get("lithology"))
        if label is not None:
            found.add(label)
    return sorted(found)
