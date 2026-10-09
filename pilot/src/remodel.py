"""Remodel projects: non-project detection (repair, signage, demolition-only) and remodel_subtype.

remodel_subtype: tenant_finish_out | interior_remodel | repair_or_other. Building use is never used (use_class is only an attribute).
Non-projects (excluded): repair, signage, demolition-only. repair_or_other is the catch-all subtype for what is left that is neither a
finish-out nor an interior remodel; repair-like rows that are caught as non-projects keep the subtype for information but are excluded.
Rules are keyword based and approximate; they are in config.yaml (filters.remodel).
"""
from __future__ import annotations
import re


def nonproject_reason(description: str | None, classes: list[str], rc: dict) -> str | None:
    text = description or ""
    cls = " ".join(classes)
    if any(k.lower() in cls.lower() for k in rc["class_signage_keywords"]):
        return "non_project_signage"
    if any(k.lower() in cls.lower() for k in rc["class_demolition_keywords"]):
        return "non_project_demolition_only"
    if re.search(rc["signage_regex"], text) and not re.search(rc["signage_override_regex"], text):
        return "non_project_signage"
    if re.search(rc["repair_regex"], text) and not re.search(rc["project_words_regex"], text):
        return "non_project_repair"
    if re.search(rc["demolition_regex"], text) and not re.search(rc["demolition_override_regex"], text):
        return "non_project_demolition_only"
    return None


def subtype(description: str | None, classes: list[str], rc: dict) -> str:
    sc, text = rc["subtype"], description or ""
    if re.search(sc["other_regex"], text) and not re.search(sc["other_override_regex"], text) and not any(re.search(sc["tenant_class_regex"], c) for c in classes):
        return "repair_or_other"                                   # equipment-type work (tower, antenna, generator, RTU...) is not a remodel of space
    if any(re.search(sc["tenant_class_regex"], c) for c in classes) or re.search(sc["tenant_desc_regex"], text):
        return "tenant_finish_out"
    if re.search(sc["interior_desc_regex"], text):
        return "interior_remodel"
    return "repair_or_other"
