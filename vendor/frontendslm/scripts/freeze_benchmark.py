"""Author the original 50-case evaluation-only pilot. Run before model inference."""
import json
from pathlib import Path

from frontendslm.io import sha256, write_json
from frontendslm.schemas import BenchmarkCase, Specification

ROOT = Path(__file__).resolve().parents[1]
GROUPS = [
    ("operations", "filter", ["robot fleet telemetry", "greenhouse sensor monitoring", "community library inventory", "harbor berth availability", "solar installation health"]),
    ("planning", "toggle", ["field research packing list", "independent film production checklist", "weekly study planner", "museum installation tasks", "community garden maintenance"]),
    ("forms", "form", ["ceramics workshop reservation", "bike repair appointment", "local volunteer signup", "observatory visit booking", "neighborhood event proposal"]),
    ("analytics", "tabs", ["urban tree canopy analytics", "fictional podcast audience insights", "household energy comparison", "water quality field survey", "cooperative grocery sales"]),
    ("catalog", "cart", ["independent bookstore catalog", "botanical print shop", "reusable camping gear rental", "small-batch tea selection", "handmade stationery store"]),
    ("learning", "accordion", ["astronomy learning guide", "public transit rider help", "open-source contribution handbook", "home composting FAQ", "printmaking course syllabus"]),
    ("configuration", "stepper", ["photography print configurator", "modular desk planner", "meal prep portion calculator", "conference badge order", "custom notebook configurator"]),
    ("editorial", "theme", ["architecture magazine article", "independent cinema journal", "marine ecology field notes", "type design portfolio", "slow travel city guide"]),
    ("directories", "sort", ["coworking space directory", "fictional hiking trail explorer", "used musical instrument listings", "local art exhibition finder", "student project showcase"]),
    ("collaboration", "dialog", ["community meeting agenda", "design studio project board", "remote book club hub", "shared workshop equipment board", "nonprofit campaign calendar"]),
]
STYLES = [
    {"descriptors": "precise, technical, restrained", "theme": "dark", "density": "medium"},
    {"descriptors": "warm, editorial, tactile", "theme": "light", "density": "low"},
    {"descriptors": "playful, geometric, colorful", "theme": "light", "density": "medium"},
    {"descriptors": "quiet, typographic, minimal", "theme": "light", "density": "low"},
    {"descriptors": "professional, high contrast, data focused", "theme": "dark", "density": "high"},
]


def step(action, test_id, value=""):
    return {"action": action, "test_id": test_id, "value": value}


WORKFLOWS = {
    "filter": ("Provide a Search input (search) and two separate items named Atlas (item-atlas) and Beacon (item-beacon). Search must filter items case-insensitively; clearing restores both.", [step("expect_visible", "item-beacon"), step("fill", "search", "Atlas"), step("expect_visible", "item-atlas"), step("expect_hidden", "item-beacon"), step("fill", "search", ""), step("expect_visible", "item-beacon")]),
    "toggle": ("Provide a task called Prepare materials, a toggle control (task-toggle), and a text status (task-status), initially Pending. Activating the control changes it to Completed; activating again restores Pending.", [step("expect_text", "task-status", "Pending"), step("click", "task-toggle"), step("expect_text", "task-status", "Completed"), step("click", "task-toggle"), step("expect_text", "task-status", "Pending")]),
    "form": ("Provide a labeled Name input (name), Email input (email), submit control (submit), and status (form-status). An empty submission must visibly say Required. After filling a name and valid email, submission must say Confirmed. Implement local validation with noValidate so an empty submission reaches the handler. Label it a demo, not a real booking.", [step("click", "submit"), step("expect_text", "form-status", "Required"), step("fill", "name", "Alex Example"), step("fill", "email", "alex@example.com"), step("click", "submit"), step("expect_text", "form-status", "Confirmed")]),
    "tabs": ("Provide Overview and Details tabs (tab-overview, tab-details) and one panel (tab-panel). It initially includes Summary; choosing Details shows Breakdown; returning to Overview shows Summary.", [step("expect_text", "tab-panel", "Summary"), step("click", "tab-details"), step("expect_text", "tab-panel", "Breakdown"), step("click", "tab-overview"), step("expect_text", "tab-panel", "Summary")]),
    "cart": ("Provide a fictional item with Add (add-item), Remove (remove-item), and cart count (cart-count). Count starts at 0, increments on Add, and decrements on Remove without becoming negative. No payment integration.", [step("expect_text", "cart-count", "0"), step("click", "add-item"), step("expect_text", "cart-count", "1"), step("click", "remove-item"), step("expect_text", "cart-count", "0")]),
    "accordion": ("Provide an expandable Getting started control (faq-toggle) and answer (faq-answer). The answer is initially hidden, then visible after activation, then hidden after a second activation. Use aria-expanded.", [step("expect_hidden", "faq-answer"), step("click", "faq-toggle"), step("expect_visible", "faq-answer"), step("click", "faq-toggle"), step("expect_hidden", "faq-answer")]),
    "stepper": ("Provide quantity controls plus (quantity-plus), minus (quantity-minus), and quantity text (quantity). Quantity starts at 1, increases to 2, decreases to 1 and cannot go below 1.", [step("expect_text", "quantity", "1"), step("click", "quantity-plus"), step("expect_text", "quantity", "2"), step("click", "quantity-minus"), step("expect_text", "quantity", "1"), step("click", "quantity-minus"), step("expect_text", "quantity", "1")]),
    "theme": ("Provide a reader appearance toggle (theme-toggle) and visible theme label (theme-label), initially Day. Activation switches the palette and label to Night; activating again restores Day.", [step("expect_text", "theme-label", "Day"), step("click", "theme-toggle"), step("expect_text", "theme-label", "Night"), step("click", "theme-toggle"), step("expect_text", "theme-label", "Day")]),
    "sort": ("Include entries Atlas and Beacon with numeric values 10 and 20. Provide a native sort select (sort) with values asc and desc, and ordered entries using data-testid=directory-item. Default ascending shows Atlas first; desc shows Beacon first. Include search (search) filtering the entries; searching Atlas leaves one entry.", [step("expect_count", "directory-item", "2"), step("select", "sort", "desc"), step("expect_text", "directory-item:first", "Beacon"), step("fill", "search", "Atlas"), step("expect_count", "directory-item", "1"), step("expect_text", "directory-item:first", "Atlas")]),
    "dialog": ("Provide a New note control (open-dialog) that opens an accessible dialog (note-dialog), a textarea (note-input), Save (save-note), and saved note region (saved-note). Save closes the dialog and shows the submitted note. The dialog should also close with Escape and restore focus.", [step("click", "open-dialog"), step("expect_visible", "note-dialog"), step("fill", "note-input", "Discuss accessibility"), step("click", "save-note"), step("expect_hidden", "note-dialog"), step("expect_text", "saved-note", "Discuss accessibility")]),
}


def main():
    cases = []
    # Interleave categories: the first 20 cover every category twice.
    for style_index, style in enumerate(STYLES):
        for category, pattern, topics in GROUPS:
            identifier = f"{category}_{style_index + 1:02d}"
            instructions, steps = WORKFLOWS[pattern]
            spec = Specification(
                project_id=identifier, application_type=category,
                user_goal=f"Build a polished single-page {topics[style_index]} interface. {instructions} Parentheses specify required data-testid values.",
                audience=["people using this service on desktop and mobile"], style=style,
                sections=["identity and navigation", "primary content", "key interaction", "supporting context"],
                interactions=[{"id": pattern, "action": instructions, "expected": "All specified state transitions work using local demonstration data."}],
                acceptance_criteria=["Required interaction test passes", "Usable at 1440px and 390px", "No horizontal overflow at 320, 390, 768, 1440, or 1920px", "Keyboard-accessible controls", "No serious or critical automated accessibility violations"],
            )
            cases.append(BenchmarkCase(id=identifier, category=category, design_family=f"{category}-{style_index}",
                difficulty="intermediate" if pattern in {"form", "dialog", "sort"} else "simple",
                spec=spec, tests=[{"id": f"{identifier}-interaction", "steps": steps}]).model_dump())
    content = "".join(json.dumps(c, ensure_ascii=False, sort_keys=True) + "\n" for c in cases).encode()
    path = ROOT / "benchmarks/pilot_v1.jsonl"
    if path.exists() and path.read_bytes() != content:
        raise SystemExit("Frozen benchmark differs; create a new version instead of overwriting")
    path.write_bytes(content)
    write_json(ROOT / "benchmarks/pilot_v1.manifest.json", {
        "schema_version": "1.0", "benchmark": "UI-Intelligence-Bench pilot v1", "sha256": sha256(content),
        "count": len(cases), "split": "evaluation", "training_use": False, "human_reviewed": False,
        "license": "MIT", "provenance": "Original authored specifications, not scraped websites.",
        "limitations": ["Small single-page pilot; advanced multi-page tasks not covered", "Template-driven acceptance workflows require independent human review"],
    })
    print(f"Frozen {len(cases)} cases: {sha256(content)}")


if __name__ == "__main__":
    main()
