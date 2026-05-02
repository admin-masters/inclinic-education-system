#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from zipfile import ZipFile

from PIL import Image

from workflow_pack_data import WORKFLOWS, select_workflows


REPO_ROOT = Path(__file__).resolve().parents[2]
DECK_DIR = REPO_ROOT / "output" / "doc" / "user-flow-decks"
PREVIEW_DIR = DECK_DIR / "previews"
QA_REPORT = DECK_DIR / "qa-summary.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run QA against the workflow deck pack.")
    parser.add_argument(
        "selectors",
        nargs="*",
        help="Optional workflow orders or slugs to QA. Defaults to the whole pack.",
    )
    parser.add_argument(
        "--workflows",
        dest="workflow_csv",
        help="Comma-separated workflow orders or slugs to QA.",
    )
    return parser.parse_args()


def run_render(selected_workflows: list[dict], selective_refresh: bool) -> list[str]:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    if selective_refresh:
        decks = [DECK_DIR / f"{workflow['order']:02d}-{workflow['slug']}.pptx" for workflow in selected_workflows]
        decks.append(DECK_DIR / "00-user-flow-training-index.pptx")
    else:
        decks = sorted(DECK_DIR.glob("*.pptx"))
    cmd = ["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(PREVIEW_DIR), *map(str, decks)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    rendered_lookup = {path.with_suffix(".pdf").name for path in decks}
    return sorted(name for name in rendered_lookup if (PREVIEW_DIR / name).exists())


def check_screenshot_dimensions(selected_workflows: list[dict]) -> dict[str, dict[str, int]]:
    dimensions = {}
    for workflow in selected_workflows:
        workflow_dir = REPO_ROOT / "docs" / "product-user-flows" / "assets" / workflow["slug"]
        for path in sorted(workflow_dir.glob("*.png")):
            with Image.open(path) as img:
                dimensions[str(path.relative_to(REPO_ROOT))] = {"width": img.width, "height": img.height}
    return dimensions


def check_index_links() -> list[str]:
    index_deck = DECK_DIR / "00-user-flow-training-index.pptx"
    with ZipFile(index_deck) as zf:
        rel = zf.read("ppt/slides/_rels/slide2.xml.rels").decode("utf-8")
    targets = []
    for workflow in WORKFLOWS:
        deck_name = f"{workflow['order']:02d}-{workflow['slug']}.pptx"
        if deck_name in rel:
            targets.append(deck_name)
    return targets


def scan_for_placeholders(selected_workflows: list[dict], selective_refresh: bool) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    if selective_refresh:
        deck_paths = [DECK_DIR / f"{workflow['order']:02d}-{workflow['slug']}.pptx" for workflow in selected_workflows]
        deck_paths.append(DECK_DIR / "00-user-flow-training-index.pptx")
    else:
        deck_paths = [deck for deck in DECK_DIR.glob("*.pptx") if deck.name != "zz-user-flow-template.pptx"]
    for deck in deck_paths:
        with ZipFile(deck) as zf:
            xml_text = "\n".join(
                zf.read(name).decode("utf-8", errors="ignore")
                for name in zf.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            )
        found = []
        for marker in ["Screenshot pending", "Insert full-width screenshot here"]:
            if marker in xml_text:
                found.append(marker)
        if found:
            hits[deck.name] = found
    return hits


def main() -> None:
    args = parse_args()
    selectors = list(args.selectors)
    if args.workflow_csv:
        selectors.append(args.workflow_csv)
    selected_workflows = select_workflows(selectors)
    selective_refresh = bool(selectors)

    rendered = run_render(selected_workflows, selective_refresh)
    dimensions = check_screenshot_dimensions(selected_workflows)
    link_targets = check_index_links()
    placeholders = scan_for_placeholders(selected_workflows, selective_refresh)
    expected_pdf_count = len(selected_workflows) + 1 if selective_refresh else len(WORKFLOWS) + 2

    report = {
        "rendered_pdfs": rendered,
        "pdf_count": len(rendered),
        "expected_pdf_count": expected_pdf_count,
        "screenshot_dimensions": dimensions,
        "linked_workflow_decks": link_targets,
        "expected_links": len(WORKFLOWS),
        "placeholder_hits": placeholders,
        "qa_scope": [f"{workflow['order']:02d}-{workflow['slug']}" for workflow in selected_workflows],
        "status": "ok" if len(rendered) >= expected_pdf_count and len(link_targets) == len(WORKFLOWS) and not placeholders else "needs_review",
    }
    QA_REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
