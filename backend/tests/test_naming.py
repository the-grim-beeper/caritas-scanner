"""This is the Miesbach scanner, not its template: no user-facing text or doc may still name
the Rhein-Neckar scanner, its live URL or its password, and the README never holds a password."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = re.compile(r"Rhein-Neckar|rhein-neckar|kurpfalz|bd635b")


def _user_facing() -> list[Path]:
    files = [ROOT / "README.md", ROOT / "frontend" / "index.html"]
    files += sorted((ROOT / "backend" / "mhs").rglob("*.py"))
    files += sorted(p for p in (ROOT / "frontend" / "src").rglob("*") if p.suffix in {".ts", ".tsx", ".css", ".html"})
    return [p for p in files if p.exists()]


def test_no_template_names_left_in_user_facing_text_or_docs():
    # Wrong: README still titled "Rhein-Neckar Horizon Scanner" with the template's live URL
    # and password; the package docstring still names the template.
    hits = [f"{p.relative_to(ROOT)}:{n}: {line.strip()}"
            for p in _user_facing()
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if TEMPLATE.search(line)]
    assert hits == []


def test_readme_names_this_scanner_and_its_live_url_but_not_the_password():
    from mhs.config import Settings

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("# Horizont-Scanner Landkreis Miesbach")
    assert "https://web-production-3e84e.up.railway.app" in readme
    assert Settings.model_fields["app_password"].default not in readme
