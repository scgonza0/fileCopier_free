import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Callable
from .models import FileInfo
from .config import filters_config_path, ensure_config_dir


CONFIG_FILE = filters_config_path()


@dataclass
class FilterRule:
    enabled: bool = True
    scan_all: bool = False
    field: str = "name"
    operator: str = "contains"
    value: str = ""


@dataclass
class FilterPreset:
    enabled: bool = True
    logic: str = "AND"
    rules: List[FilterRule] = field(default_factory=list)


# ─── Eval ─────────────────────────────────────────────────


def evaluate_rule(fi: FileInfo, rule: FilterRule) -> bool:
    if not rule.enabled or not rule.value:
        return True  # rule disabled or empty = no filter

    val_lower = rule.value.strip().lower()
    name_lower = fi.name.lower()
    path_lower = fi.relative_path.lower()
    ext = fi.extension

    if rule.field == "name":
        # El nombre se compara SIN la extensión; la extensión es un campo aparte.
        if fi.extension:
            stem_lower = fi.name[: -len(fi.extension)].lower()
        else:
            stem_lower = name_lower
        return _eval_str(stem_lower, rule.operator, val_lower)

    elif rule.field == "extension":
        if rule.operator == "is":
            return ext == (val_lower if val_lower.startswith(".") else f".{val_lower}")
        elif rule.operator == "is_not":
            return ext != (val_lower if val_lower.startswith(".") else f".{val_lower}")
        elif rule.operator == "is_one_of":
            exts = [e.strip().lower() for e in rule.value.split(",") if e.strip()]
            exts = [e if e.startswith(".") else f".{e}" for e in exts]
            return ext in exts

    elif rule.field == "path":
        return _eval_str(path_lower, rule.operator, val_lower)

    elif rule.field == "size":
        return _eval_size(fi.size, rule.operator, rule.value)

    elif rule.field == "date":
        return _eval_date(fi.modified, rule.operator, rule.value)

    elif rule.field == "hidden":
        name = fi.name
        is_hidden = name.startswith(".")
        if rule.value.strip().lower() in ("si", "yes", "1", "true"):
            return is_hidden
        else:
            return not is_hidden

    return True


def _eval_str(text: str, operator: str, pattern: str) -> bool:
    if operator == "contains":
        return pattern in text
    elif operator == "not_contains":
        return pattern not in text
    elif operator == "equals":
        return text == pattern
    elif operator == "starts_with":
        return text.startswith(pattern)
    elif operator == "ends_with":
        return text.endswith(pattern)
    elif operator == "regex":
        try:
            return bool(re.search(pattern, text))
        except re.error:
            return False
    return True


def _eval_size(file_bytes: int, operator: str, value_str: str) -> bool:
    if operator == "between":
        parts = value_str.split(",")
        if len(parts) == 2:
            try:
                lo = parse_size(parts[0].strip())
                hi = parse_size(parts[1].strip())
                return lo <= file_bytes <= hi
            except ValueError:
                pass
        return True

    try:
        val = parse_size(value_str)
    except ValueError:
        return True

    if operator == "gt":
        return file_bytes > val
    elif operator == "lt":
        return file_bytes < val
    return True


def _parse_date_value(text: str) -> Optional[datetime]:
    """Parse ISO dates, optionally with time. Returns None on failure."""
    t = text.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(t, fmt)
        except ValueError:
            continue
    return None


def _eval_date(file_dt: datetime, operator: str, value_str: str) -> bool:
    now = datetime.now()

    if operator == "last_n_days":
        try:
            n = int(value_str.strip())
            return file_dt >= now - timedelta(days=n)
        except ValueError:
            return True

    if operator in ("before", "after", "between"):
        if operator in ("before", "after"):
            d = _parse_date_value(value_str)
            if d is None:
                return True
            if operator == "before":
                return file_dt < d
            else:
                return file_dt > d
        elif operator == "between":
            parts = value_str.split(",")
            if len(parts) == 2:
                d1 = _parse_date_value(parts[0])
                d2 = _parse_date_value(parts[1])
                if d1 is not None and d2 is not None:
                    return d1 <= file_dt <= d2
    return True


def parse_size(text: str) -> int:
    text = text.strip().lower()
    multipliers = {"b": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3}
    for suffix in ("gb", "mb", "kb", "b"):  # longest first so "500mb" matches "mb"
        if text.endswith(suffix):
            num = float(text[: -len(suffix)].strip())
            return int(num * multipliers[suffix])
    return int(float(text))


# ─── Match ─────────────────────────────────────────────────


def match(preset: FilterPreset, files: List[FileInfo],
          progress_callback: Optional[Callable] = None) -> List[FileInfo]:
    if not preset.enabled:
        return list(files)
    enabled = [r for r in preset.rules if r.enabled]
    if not enabled:
        return list(files)

    from .logger import log
    log(f"match INICIO: {len(files)} archivos | {len(enabled)} reglas activas")

    results = []
    if preset.logic == "AND":
        for idx, fi in enumerate(files):
            if all(evaluate_rule(fi, r) for r in enabled):
                results.append(fi)
            if progress_callback and idx % 20000 == 0:
                progress_callback(idx, len(files))
    else:
        for idx, fi in enumerate(files):
            if any(evaluate_rule(fi, r) for r in enabled):
                results.append(fi)
            if progress_callback and idx % 20000 == 0:
                progress_callback(idx, len(files))
    if progress_callback:
        progress_callback(len(files), len(files))
    log(f"match FIN: {len(results)} resultados")
    return results


# ─── Persistencia ──────────────────────────────────────────


def load_preset() -> FilterPreset:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        preset = FilterPreset(
            enabled=data.get("enabled", True),
            logic=data.get("logic", "AND"),
        )
        for rd in data.get("rules", []):
            preset.rules.append(FilterRule(
                enabled=rd.get("enabled", False),
                scan_all=rd.get("scan_all", False),
                field=rd.get("field", "name"),
                operator=rd.get("operator", "contains"),
                value=rd.get("value", ""),
            ))
        _log_preset("load", preset)
        return preset
    except (FileNotFoundError, json.JSONDecodeError):
        return FilterPreset()


def save_preset(preset: FilterPreset):
    data = {
        "enabled": preset.enabled,
        "logic": preset.logic,
        "rules": [
            {
                "enabled": r.enabled,
                "scan_all": r.scan_all,
                "field": r.field,
                "operator": r.operator,
                "value": r.value,
            }
            for r in preset.rules
        ],
    }
    ensure_config_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    _log_preset("save", preset)


def _log_preset(action: str, preset: FilterPreset):
    try:
        from .logger import log
        rules = ", ".join(
            f"{r.field} {r.operator} '{r.value}'" + (" [ScanAll]" if r.scan_all else "")
            for r in preset.rules if r.enabled
        ) or "(ninguna regla activa)"
        log(f"Preset {action}: enabled={preset.enabled} logic={preset.logic} reglas=[{rules}]")
    except Exception:
        pass
