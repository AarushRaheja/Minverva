"""One-line project briefs with real variety, and train/dev/test splits that do not leak.

The original generator (slm/bench/projects.py) renders exactly one multi-line brief per template, so
its 120 training rows hold 8 distinct briefs, dev repeats them, and the brief itself spells out the
split. Here each brief is one line, and the manager has to work out the tasks from it.

Leakage rules, asserted by tests/test_bench_variety.py:
  - train, dev and test use disjoint concepts AND disjoint entity names;
  - test also uses phrasings that train and dev never saw;
  - no brief appears twice, within or across splits.

Every brief names its entities, its form entity and any OAuth requirement, so the gold plan is a
function of the brief and a perfect score is possible. Inferring unnamed entities is out of scope.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from slm.bench.catalog import STACK, Template_, build_plan
from slm.contracts import Project
from slm.domains import plural


@dataclass(frozen=True)
class Concept:
    id: str
    name: str
    article: str
    entities: tuple[str, ...]


def _c(cid: str, name: str, article: str, *entities: str) -> Concept:
    return Concept(cid, name, article, entities)


TRAIN_CONCEPTS: tuple[Concept, ...] = (
    _c("invoice_tracker", "invoice tracker", "an invoice tracker for a design studio",
       "invoice", "client", "payment", "receipt"),
    _c("issue_board", "issue board", "an issue board for an engineering team",
       "issue", "project", "milestone", "label"),
    _c("room_booking", "room booking service", "a room booking service for an office",
       "booking", "room", "building", "amenity_item"),
    _c("course_platform", "course platform", "a course platform for a coding bootcamp",
       "course", "enrollment", "lesson", "assessment"),
    _c("expense_log", "expense log", "an expense log for freelancers",
       "expense", "tag", "report", "vendor"),
    _c("stock_room", "inventory service", "an inventory service for a stock room",
       "item", "supplier", "shipment", "warehouse"),
    _c("chat_service", "chat service", "a chat service for remote teams",
       "message", "channel", "thread", "reaction"),
    _c("survey_tool", "survey tool", "a survey tool for internal feedback",
       "survey", "response", "question", "respondent"),
    _c("gym_tracker", "gym tracker", "a gym tracker for personal trainers",
       "workout", "exercise", "member", "goal"),
    _c("clinic_desk", "clinic scheduler", "a clinic scheduler for a family practice",
       "appointment", "patient", "doctor", "prescription"),
    _c("library_desk", "library desk", "a library desk app for a town library",
       "book", "loan", "reader", "author"),
    _c("event_planner", "event planner", "an event planner for a conference team",
       "event", "speaker", "venue", "attendee"),
    _c("fleet_log", "fleet log", "a fleet log for a delivery company",
       "vehicle", "driver", "trip", "repair"),
    _c("crm_lite", "small CRM", "a small CRM for a sales team",
       "lead", "account", "deal", "contact"),
    _c("hiring_board", "hiring board", "a hiring board for a startup",
       "candidate", "job", "interview", "offer"),
    _c("kitchen_orders", "kitchen order system", "a kitchen order system for a restaurant",
       "entree", "ticket_item", "ingredient", "menu"),
    _c("property_desk", "property manager", "a property manager for small landlords",
       "apartment", "tenant", "lease", "rent_charge"),
    _c("volunteer_hub", "volunteer hub", "a volunteer hub for a food bank",
       "volunteer", "shift", "donation", "site"),
    _c("pet_clinic", "pet records app", "a pet records app for a vet",
       "pet", "owner", "visit", "vaccine"),
    _c("garden_log", "garden log", "a garden log for a community garden",
       "plot", "plant", "harvest", "gardener"),
    _c("travel_notes", "trip planner", "a trip planner for small groups",
       "trip_plan", "stop", "traveler", "reservation"),
    _c("studio_time", "studio scheduler", "a studio scheduler for a music school",
       "lesson_slot", "instructor", "student", "instrument"),
    _c("repair_shop", "repair shop tracker", "a repair shop tracker for a bike store",
       "work_ticket", "bike", "part", "mechanic"),
    _c("press_room", "newsroom planner", "a newsroom planner for a local paper",
       "article", "editor", "section", "deadline"),
    _c("league_table", "league manager", "a league manager for a youth soccer club",
       "team", "player", "game", "coach"),
    _c("farm_market", "market stall app", "a market stall app for local farmers",
       "stall", "product", "farmer", "sale"),
    _c("lab_notebook", "lab notebook", "a lab notebook for a biology lab",
       "experiment", "sample", "protocol", "result"),
    _c("podcast_desk", "podcast planner", "a podcast planner for an indie network",
       "episode", "guest", "show", "sponsor"),
    _c("laundry_route", "laundry pickup app", "a laundry pickup app for a neighborhood shop",
       "pickup", "customer", "garment", "route_stop"),
    _c("museum_desk", "museum catalog", "a museum catalog for a small gallery",
       "artwork", "artist", "exhibit", "loan_record"),
)

DEV_CONCEPTS: tuple[Concept, ...] = (
    _c("tutoring_desk", "tutoring desk", "a tutoring desk for a high school",
       "tutor", "pupil", "homework", "subject"),
    _c("charter_boats", "boat charter app", "a boat charter app for a marina",
       "boat", "skipper", "charter", "dock"),
    _c("salon_book", "salon scheduler", "a salon scheduler for a hair studio",
       "stylist", "treatment", "visitor", "voucher"),
    _c("brew_log", "brewery log", "a brewery log for a craft brewer",
       "batch", "recipe_card", "fermenter", "keg"),
    _c("camp_desk", "summer camp desk", "a summer camp desk for a youth program",
       "camper", "cabin", "workshop", "counselor"),
    _c("film_slate", "film production tracker", "a film production tracker for an indie crew",
       "scene", "actor", "prop", "crew_member"),
    _c("thrift_shop", "thrift shop register", "a thrift shop register for a charity store",
       "listing", "consignor", "markdown", "register"),
    _c("beekeeper_log", "beekeeping log", "a beekeeping log for a hobby apiary",
       "hive", "inspection", "queen", "honey_jar"),
)

TEST_CONCEPTS: tuple[Concept, ...] = (
    _c("ticket_desk", "support ticket desk", "a support ticket desk for a SaaS product",
       "ticket", "agent", "escalation", "macro"),
    _c("recipe_box", "recipe box", "a recipe box for home cooks",
       "recipe", "collection", "cook", "pantry_item"),
    _c("observatory_log", "observatory log", "an observatory log for an astronomy society",
       "telescope", "observation", "astronomer", "comet"),
    _c("ferry_desk", "ferry booking desk", "a ferry booking desk for an island operator",
       "vessel", "sailing", "passenger", "harbor"),
    _c("vineyard_book", "vineyard ledger", "a vineyard ledger for a family winery",
       "vine", "vintage", "barrel", "cellar"),
    _c("climbing_gym", "climbing gym app", "a climbing gym app for route setters",
       "wall", "boulder", "climber", "belay_check"),
    _c("choir_desk", "choir manager", "a choir manager for a community chorus",
       "singer", "rehearsal", "score_sheet", "concert"),
    _c("archive_desk", "archive tracker", "an archive tracker for a county records office",
       "manuscript", "archivist", "storage_box", "accession"),
    _c("ski_patrol", "ski patrol log", "a ski patrol log for a mountain resort",
       "patroller", "incident", "slope", "lift"),
    _c("bakery_line", "bakery planner", "a bakery planner for a neighborhood bakery",
       "bread_tray", "baker", "oven", "dough_mix"),
)

SHARED_PHRASINGS: tuple[str, ...] = (
    "Build {article} that manages {items}, with a create form for {form}{auth}.",
    "Create {article} covering {items}; people add new {form} through a form{auth}.",
    "I need {article} to keep track of {items}, plus a form for adding {form}{auth}.",
    "Develop {article} with pages for {items} and a form to create {form}{auth}.",
    "Make {article} where people can browse {items} and submit new {form}{auth}.",
    "We want {article} handling {items}, where a form adds new {form}{auth}.",
)
TEST_PHRASINGS: tuple[str, ...] = (
    "Ship {article}: it handles {items}, and {form} get created from a form{auth}.",
    "Put together {article} around {items}, including a simple form for entering {form}{auth}.",
)

SHARED_OAUTH = (", and sign-in through OAuth", ", and let people log in with an OAuth provider")
TEST_OAUTH = (", with third-party OAuth login",)
NO_OAUTH = ("", ", using plain session login")

# Entity count mix: mostly two or three, with enough of one and four to teach the pattern.
_COUNTS, _WEIGHTS = (1, 2, 3, 4), (15, 40, 30, 15)
_MAX_TRIES = 500


def concepts_for(split: str) -> tuple[Concept, ...]:
    return {"train": TRAIN_CONCEPTS, "dev": DEV_CONCEPTS, "test": TEST_CONCEPTS}[split]


def _words(entity: str) -> str:
    """line_item -> line items"""
    return plural(entity).replace("_", " ")


def _join(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def _draw(concept: Concept, split: str, rng: random.Random) -> tuple[Template_, str]:
    entities = tuple(rng.sample(concept.entities, rng.choices(_COUNTS, _WEIGHTS)[0]))
    form = rng.choice(entities)
    oauth = rng.random() < 0.5
    phrasings = TEST_PHRASINGS if split == "test" else SHARED_PHRASINGS
    oauth_text = TEST_OAUTH if split == "test" else SHARED_OAUTH
    brief = rng.choice(phrasings).format(
        article=concept.article,
        items=_join([_words(e) for e in entities]),
        form=_words(form),
        auth=rng.choice(oauth_text if oauth else NO_OAUTH),
    )
    brief = brief[0].upper() + brief[1:]
    return Template_(concept.id, concept.name, concept.article, entities, form, oauth), brief


def generate_varied(n: int, split: str, seed: int) -> list[Project]:
    """n distinct one-line projects, balanced across the split's concepts.

    Prefix-stable: the first k projects are the same for any n >= k.
    """
    pool = concepts_for(split)
    seen: set[str] = set()
    out: list[Project] = []
    for i in range(n):
        concept = pool[i % len(pool)]
        for attempt in range(_MAX_TRIES):
            rng = random.Random(f"varied:{seed}:{split}:{i}:{attempt}")
            tpl, brief = _draw(concept, split, rng)
            if brief not in seen:
                break
        else:
            raise ValueError(f"concept {concept.id} ran out of distinct briefs at project {i}")
        seen.add(brief)
        plan = build_plan(tpl)
        assert plan.stack == STACK
        out.append(Project(
            id=f"proj-{split}-{concept.id}-s{seed}-{i}",
            source="synthetic",
            split=split,  # type: ignore[arg-type]
            description=brief,
            plan=plan,
            n_tasks=len(plan.tasks),
            depth=len(plan.levels()),
            template_id=concept.id,
        ))
    return out
