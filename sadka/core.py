"""Infrastructure: config loading, project paths, table IO, run provenance, small stats utils."""
from pathlib import Path
import numpy as np
from scipy import stats
import hashlib
import pandas as pd
import json
import platform
import re
import subprocess
import sys
import yaml


# ===== from paths.py =====
def project_root() -> Path:
    # this file: <root>/sadka/core.py  ->  parents[1] == <root>
    return Path(__file__).resolve().parents[1]


def resolve(rel) -> Path:
    """Resolve a path that may be relative to the project root."""
    p = Path(rel)
    return p if p.is_absolute() else (project_root() / p).resolve()


def ensure_dir(rel) -> Path:
    p = resolve(rel)
    p.mkdir(parents=True, exist_ok=True)
    return p


# ===== from utils.py =====
def pvalue_from_corr(r: float, n: int = 180) -> float:
    """Two-sided p-value for a Pearson correlation r with sample size n."""
    r = float(r)
    if abs(r) >= 1.0:
        return 0.0
    t = r * np.sqrt((n - 2) / (1.0 - r**2))
    return float(2 * stats.t.sf(abs(t), df=n - 2))


# ===== from io.py =====
def sha256_file(path) -> str:
    h = hashlib.sha256()
    h.update(Path(resolve(path)).read_bytes())
    return h.hexdigest()


def read_table(path, **kw) -> pd.DataFrame:
    """Read csv/tsv/parquet/xls/xlsx by extension."""
    p = Path(resolve(path))
    suf = p.suffix.lower()
    if suf in (".csv",):
        return pd.read_csv(p, **kw)
    if suf in (".tsv", ".txt"):
        return pd.read_csv(p, sep="\t", **kw)
    if suf in (".parquet",):
        return pd.read_parquet(p, **kw)
    if suf in (".xls",):
        return pd.read_excel(p, engine="xlrd", **kw)
    if suf in (".xlsx", ".xlsm"):
        return pd.read_excel(p, engine="openpyxl", **kw)
    raise ValueError(f"Unsupported table extension: {suf} ({p})")


# ===== from provenance.py =====
PROJECT_DIRNAME = "6.7复现另一篇"


def sanitize_local_paths(text: str) -> str:
    """Scrub local username and project absolute path from provenance text.
    Handles \\, \\\\ (JSON-escaped), and / separators, case-insensitively."""
    # C:\Users\<user>\  /  C:\\Users\\<user>\\  /  C:/Users/<user>/  ->  <USER>
    text = re.sub(
        r"([Cc]:[\\/]{1,2}[Uu]sers[\\/]{1,2})([^\\/\"]+)([\\/]{1,2})",
        r"\1<USER>\3",
        text,
    )
    # Editable local install line (path may contain spaces) -> "-e ."
    text = re.sub(rf"(?im)^-e\s+.*{re.escape(PROJECT_DIRNAME)}.*$", "-e .", text)
    # Any remaining file:// URL pointing at the project dir -> "."
    text = re.sub(rf"file:[\\/]+\S*{re.escape(PROJECT_DIRNAME)}\S*", ".", text, flags=re.IGNORECASE)
    # Belt-and-suspenders: collapse any leftover absolute path to the project dir.
    text = re.sub(rf"[A-Za-z]:[\\/].*?{re.escape(PROJECT_DIRNAME)}", ".", text)
    return text


def write_sanitized_copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(sanitize_local_paths(src.read_text(encoding="utf-8")), encoding="utf-8")


def write_env_lock(stage: str = "stage02") -> dict:
    logs = ensure_dir("outputs/logs")
    # python version (write sanitized directly - low risk, only the exe path is local)
    (logs / "python_version.txt").write_text(
        sanitize_local_paths(f"{sys.version}\nexecutable: {sys.executable}\n"), encoding="utf-8"
    )
    freeze = subprocess.run(
        [sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True
    ).stdout
    raw = logs / f"pip_freeze_{stage}.txt"
    raw.write_text(freeze, encoding="utf-8")
    san = logs / f"pip_freeze_{stage}_sanitized.txt"
    san.write_text(sanitize_local_paths(freeze), encoding="utf-8")
    return {"package_lock_file": f"outputs/logs/pip_freeze_{stage}_sanitized.txt"}


def write_run_manifest(stage: str, extra: dict | None = None) -> Path:
    logs = ensure_dir("outputs/logs")
    env = write_env_lock(stage)
    manifest = {
        "stage": stage,
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "python_version_full": sys.version,
        "platform": platform.platform(),
        "package_lock_file": env["package_lock_file"],
    }
    if extra:
        manifest.update(extra)
    text = json.dumps(manifest, indent=2, default=str)
    raw = logs / "run_manifest.json"            # gitignored (local only)
    raw.write_text(text, encoding="utf-8")
    san = logs / "run_manifest_sanitized.json"  # committable
    san.write_text(sanitize_local_paths(text), encoding="utf-8")
    return san


# ===== from config.py =====
def load_yaml(path) -> dict:
    p = resolve(path)
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {p}")
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config(path="config/spec_table3_main.yaml") -> dict:
    """Load the main spec config."""
    return load_yaml(path)


def load_style_map(path="config/style_map.yaml") -> dict:
    return load_yaml(path)


def load_factor_sets(path="config/factor_sets.yaml") -> dict:
    return load_yaml(path)

