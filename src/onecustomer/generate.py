"""Synthetic world: real people, two source systems that see them imperfectly, 24 monthly loads.

The ground truth is a population of households. Each person may hold a loan, a card, or both. The
``loans`` system is an older branch-captured platform: upper-case names, IDs nearly always present,
phone numbers that go stale. The ``cards`` system is app-onboarded: tidy names and emails, but
nicknames, missing IDs on legacy accounts and the odd day/month swap.

Over 24 months people move house, change phone numbers, marry and change surname, open a second
product, and get re-onboarded as a duplicate. Each system learns about a change with its own lag,
and sometimes never. Data remediation fixes some ID typos and back-fills some missing IDs.

The hard negatives are deliberate: twins (same surname, date of birth and address, IDs a few digits
apart), fathers and sons with the same name at the same address, and household members whose phone
number was captured on each other's records.

Output (``data/``):
- ``versions.parquet``: one row per source-record version, keyed by ``record_key`` and ``load_month``
- ``links.parquet``: ``record_key -> person_id`` ground truth (never shown to the matcher)
- ``people.parquet``: the true population with household, twin and junior flags
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from . import reference as ref
from .sa_id import make_id

N_MONTHS = 24
SYSTEMS = ("loans", "cards")
KEY_PREFIX = {"loans": "LN", "cards": "CD"}
VERSION_COLUMNS = [
    "system", "record_key", "load_month", "first_name", "middle_name", "surname", "national_id",
    "dob", "phone", "email", "address_line", "city", "postal_code", "balance",
]


def month_end(m: int) -> date:
    """Load date for month ``m`` (1 = January 2024, 24 = December 2025)."""
    year, month = 2024 + (m - 1) // 12, (m - 1) % 12 + 1
    first_of_next = date(year + (month == 12), month % 12 + 1, 1)
    return first_of_next - timedelta(days=1)


@dataclass(frozen=True)
class WorldConfig:
    """Every rate in the synthetic world. Monthly rates are per person (or household) per month."""

    p_both: float = 0.45
    p_loans_only: float = 0.30
    p_legacy: float = 0.80  # first product already on the books at month 1
    p_second_product_later: float = 0.40  # cross-sell during the 24 months
    p_duplicate: tuple[tuple[str, float], ...] = (("loans", 0.02), ("cards", 0.04))
    p_twins: float = 0.15  # per child slot after the first child
    p_junior: float = 0.10  # son named after his father
    # Capture noise at onboarding
    p_id_missing: tuple[tuple[str, float], ...] = (("loans", 0.02), ("cards", 0.22))
    p_id_typo: tuple[tuple[str, float], ...] = (("loans", 0.015), ("cards", 0.01))
    p_first_typo: tuple[tuple[str, float], ...] = (("loans", 0.03), ("cards", 0.02))
    p_surname_typo: tuple[tuple[str, float], ...] = (("loans", 0.02), ("cards", 0.015))
    p_nickname: float = 0.25  # cards only, when the first name has a known short form
    p_dob_swap: float = 0.02  # cards only, day/month swapped when day <= 12
    p_phone_missing: tuple[tuple[str, float], ...] = (("loans", 0.15), ("cards", 0.03))
    p_phone_of_relative: float = 0.03  # a household member's number captured instead
    p_email_missing: tuple[tuple[str, float], ...] = (("loans", 0.75), ("cards", 0.08))
    # Life events
    p_move: float = 0.012  # per household per month
    p_phone_change: float = 0.008
    p_email_change: float = 0.003
    p_marriage: float = 0.002  # women aged 22-45 with their own surname
    # How fast each system learns about a change: (probability it never does, mean lag in months)
    lag_address: tuple[tuple[str, float, float], ...] = (("loans", 0.15, 2.0), ("cards", 0.05, 0.5))
    lag_phone: tuple[tuple[str, float, float], ...] = (("loans", 0.30, 3.0), ("cards", 0.05, 0.2))
    lag_surname: tuple[tuple[str, float, float], ...] = (("loans", 0.20, 2.0), ("cards", 0.35, 1.0))
    lag_email: tuple[tuple[str, float, float], ...] = (("loans", 0.60, 2.0), ("cards", 0.02, 0.1))
    # Remediation (per affected record per month)
    p_fix_id_typo: float = 0.04
    p_backfill_id: float = 0.015  # cards records with no ID

    def by_system(self, name: str, system: str) -> float:
        return dict(getattr(self, name))[system]

    def lag(self, group: str, system: str) -> tuple[float, float]:
        for s, never, mean in getattr(self, f"lag_{group}"):
            if s == system:
                return never, mean
        raise KeyError(system)


# --------------------------------------------------------------------------------------- people


def _zipf(n: int, s: float = 0.8) -> np.ndarray:
    w = 1.0 / np.arange(1, n + 1) ** s
    return w / w.sum()


def _random_dob(rng: np.random.Generator, age_low: int, age_high: int) -> date:
    days = int(rng.integers(age_low * 365, age_high * 365))
    return date(2024, 1, 1) - timedelta(days=days)


def _random_address(rng: np.random.Generator) -> tuple[str, str, str]:
    city = list(ref.CITIES)[int(rng.integers(len(ref.CITIES)))]
    low, high = ref.CITIES[city]
    street = ref.STREETS[int(rng.integers(len(ref.STREETS)))]
    return f"{int(rng.integers(1, 400))} {street}", city, f"{int(rng.integers(low, high + 1)):04d}"


class _Population:
    def __init__(self, rng: np.random.Generator, cfg: WorldConfig):
        self.rng, self.cfg = rng, cfg
        self.people: list[dict] = []
        self.used_ids: set[str] = set()
        self.used_phones: set[str] = set()
        self.used_emails: set[str] = set()
        self.surname_w = _zipf(len(ref.SURNAMES))

    def surname(self) -> str:
        return ref.SURNAMES[int(self.rng.choice(len(ref.SURNAMES), p=self.surname_w))]

    def first(self, gender: str, exclude: str | None = None) -> str:
        pool = ref.FEMALE_FIRST if gender == "F" else ref.MALE_FIRST
        while True:
            name = pool[int(self.rng.integers(len(pool)))]
            if name != exclude:
                return name

    def national_id(self, dob: date, gender: str, near: str | None = None) -> str:
        female = gender == "F"
        if near is not None:  # twins are registered together: consecutive sequence numbers
            base = int(near[6:10]) % 5000
            for step in range(1, 50):
                seq = (base + step) % 5000
                nid = make_id(dob, female, seq)
                if nid not in self.used_ids:
                    self.used_ids.add(nid)
                    return nid
        while True:
            citizen = 1 if self.rng.random() < 0.05 else 0
            nid = make_id(dob, female, int(self.rng.integers(5000)), citizen)
            if nid not in self.used_ids:
                self.used_ids.add(nid)
                return nid

    def phone(self) -> str:
        while True:
            prefix = ref.MOBILE_PREFIXES[int(self.rng.integers(len(ref.MOBILE_PREFIXES)))]
            number = prefix + f"{int(self.rng.integers(10_000_000)):07d}"
            if number not in self.used_phones:
                self.used_phones.add(number)
                return number

    def email(self, first: str, surname: str) -> str | None:
        if self.rng.random() < 0.12:
            return None
        local_base = f"{first}.{surname}".lower().replace(" ", "")
        domain = ref.EMAIL_DOMAINS[int(self.rng.integers(len(ref.EMAIL_DOMAINS)))]
        local = local_base
        while f"{local}@{domain}" in self.used_emails:
            local = f"{local_base}{int(self.rng.integers(1, 99))}"
        self.used_emails.add(f"{local}@{domain}")
        return f"{local}@{domain}"

    def add(self, hh: int, gender: str, first: str, surname: str, dob: date, address, **flags) -> dict:
        rng = self.rng
        middle = self.first(gender, exclude=first) if rng.random() < 0.55 else None
        person = {
            "person_id": f"P{len(self.people) + 1:06d}",
            "household_id": hh,
            "gender": gender,
            "first": first,
            "middle": middle,
            "surname": surname,
            "dob": dob,
            "national_id": self.national_id(dob, gender, near=flags.get("twin_id")),
            "phone": self.phone(),
            "address": address,
            "twin_of": flags.get("twin_of"),
            "junior_of": flags.get("junior_of"),
            "ver": {"address": 0, "phone": 0, "surname": 0, "email": 0},
        }
        person["email"] = self.email(first, surname)
        self.people.append(person)
        return person

    def build(self, n_people: int) -> list[dict]:
        rng, cfg = self.rng, self.cfg
        hh = 0
        while len(self.people) < n_people:
            hh += 1
            size = int(rng.choice([1, 2, 3, 4], p=[0.45, 0.30, 0.15, 0.10]))
            size = min(size, n_people - len(self.people))
            address = _random_address(rng)
            surname = self.surname()
            head_gender = "M" if rng.random() < 0.5 else "F"
            head_age = (40, 72) if size >= 3 else (21, 75)
            head = self.add(hh, head_gender, self.first(head_gender), surname,
                            _random_dob(rng, *head_age), address)
            members = [head]
            if size >= 2:
                g = ("F" if head_gender == "M" else "M") if rng.random() < 0.85 else head_gender
                married = rng.random() < 0.7
                head_age = 2024 - head["dob"].year
                spouse_dob = _random_dob(rng, max(21, head_age - 6), max(23, head_age + 6))
                spouse = self.add(hh, g, self.first(g, exclude=head["first"]),
                                  surname if married else self.surname(), spouse_dob, address)
                members.append(spouse)
            father = next((m for m in members if m["gender"] == "M"), None)
            previous_child = None
            for _ in range(size - len(members)):
                g = "M" if rng.random() < 0.5 else "F"
                if previous_child is not None and rng.random() < cfg.p_twins:
                    child = self.add(hh, g, self.first(g, exclude=previous_child["first"]), surname,
                                     previous_child["dob"], address,
                                     twin_of=previous_child["person_id"],
                                     twin_id=previous_child["national_id"])
                elif g == "M" and father is not None and rng.random() < cfg.p_junior:
                    father_age = 2024 - father["dob"].year
                    lo = max(18, father_age - 40)
                    hi = max(lo + 1, min(32, father_age - 18))
                    child = self.add(hh, g, father["first"], surname, _random_dob(rng, lo, hi),
                                     address, junior_of=father["person_id"])
                else:
                    hi = max(19, min(34, 2024 - head["dob"].year - 19))
                    child = self.add(hh, g, self.first(g), surname, _random_dob(rng, 18, hi), address)
                previous_child = child
        return self.people


# ---------------------------------------------------------------------------------- capture noise

_LETTERS = "abcdefghijklmnopqrstuvwxyz"


def _typo(rng: np.random.Generator, text: str) -> str:
    """One keystroke error: substitute, delete, double or swap adjacent characters."""
    if len(text) < 4:
        return text
    i = int(rng.integers(1, len(text) - 1))  # keep the first letter: capture errors rarely hit it
    kind = int(rng.integers(4))
    if kind == 0:
        c = _LETTERS[int(rng.integers(26))]
        c = c.upper() if text[i].isupper() else c
        return text[:i] + c + text[i + 1 :] if c != text[i] else text[:i] + text[i + 1 :]
    if kind == 1:
        return text[:i] + text[i + 1 :]
    if kind == 2:
        return text[:i] + text[i] + text[i:]
    if text[i] == text[i + 1]:
        return text[:i] + text[i + 1 :]
    return text[:i] + text[i + 1] + text[i] + text[i + 2 :]


def _id_typo(rng: np.random.Generator, nid: str) -> str:
    """A digit mistyped or two adjacent digits swapped."""
    while True:
        i = int(rng.integers(0, 12))
        if rng.random() < 0.5 and nid[i] != nid[i + 1]:
            return nid[:i] + nid[i + 1] + nid[i] + nid[i + 2 :]
        d = str(int(rng.integers(10)))
        if d != nid[i]:
            return nid[:i] + d + nid[i + 1 :]


def _fmt_surname(rng: np.random.Generator, system: str, surname: str) -> str:
    if system == "loans":
        s = surname.upper()
        if " " in s:
            r = rng.random()
            if r < 0.10:
                s = s.replace(" ", "")
            elif r < 0.20 and s.startswith("VAN DER "):
                s = "VD " + s[len("VAN DER ") :]
        return s
    if " " in surname and rng.random() < 0.3:
        return surname.title()
    return surname


def _fmt_phone(rng: np.random.Generator, system: str, phone: str) -> str:
    if system == "loans":
        return phone if rng.random() < 0.7 else f"{phone[:3]} {phone[3:6]} {phone[6:]}"
    if rng.random() < 0.6:
        return f"+27 {phone[1:3]} {phone[3:6]} {phone[6:]}"
    return "+27" + phone[1:]


def _fmt_address(rng: np.random.Generator, system: str, address) -> tuple[str, str, str]:
    line, city, postal = address
    if system == "loans":
        return line.upper(), city.upper(), postal
    if rng.random() < 0.5:
        for long, short in ref.STREET_ABBREVIATIONS.items():
            line = line.replace(long, short)
    return line, city, postal


def _fmt_email(rng: np.random.Generator, system: str, email: str | None) -> str | None:
    if email is None:
        return None
    if system == "cards" and rng.random() < 0.1:
        return email[0].upper() + email[1:]
    return email


class _Systems:
    def __init__(self, rng: np.random.Generator, cfg: WorldConfig, population: _Population):
        self.rng, self.cfg, self.population = rng, cfg, population
        people = self.people = population.people
        self.by_pid = {p["person_id"]: p for p in people}
        self.households: dict[int, list[dict]] = defaultdict(list)
        for p in people:
            self.households[p["household_id"]].append(p)
        self.records: dict[str, dict] = {}
        self.records_of: dict[str, list[str]] = defaultdict(list)
        self.counter = {s: 0 for s in SYSTEMS}
        self.pending: dict[int, list[tuple[str, str, int, object]]] = defaultdict(list)

    def capture(self, system: str, person: dict, month: int) -> str:
        rng, cfg = self.rng, self.cfg
        self.counter[system] += 1
        key = f"{KEY_PREFIX[system]}{self.counter[system]:07d}"

        first = person["first"]
        if system == "cards" and first.upper() in ref.NICKNAMES and rng.random() < cfg.p_nickname:
            first = ref.NICKNAMES[first.upper()].title()
        if rng.random() < cfg.by_system("p_first_typo", system):
            first = _typo(rng, first)
        middle = person["middle"]
        if middle is not None:
            r = rng.random()
            if system == "loans":
                middle = middle if r < 0.6 else (middle[0] if r < 0.85 else None)
            else:
                middle = middle if r < 0.3 else None
        surname = _fmt_surname(rng, system, person["surname"])
        if rng.random() < cfg.by_system("p_surname_typo", system):
            surname = _typo(rng, surname)

        nid, id_status = person["national_id"], "ok"
        if rng.random() < cfg.by_system("p_id_missing", system):
            nid, id_status = None, "missing"
        elif rng.random() < cfg.by_system("p_id_typo", system):
            nid, id_status = _id_typo(rng, nid), "typo"

        dob = person["dob"]
        if system == "cards" and dob.day <= 12 and dob.day != dob.month and rng.random() < cfg.p_dob_swap:
            dob = date(dob.year, dob.day, dob.month)

        phone = person["phone"]
        relatives = [m for m in self.households[person["household_id"]] if m is not person]
        if relatives and rng.random() < cfg.p_phone_of_relative:
            phone = relatives[int(rng.integers(len(relatives)))]["phone"]
        if rng.random() < cfg.by_system("p_phone_missing", system):
            phone = None

        email = person["email"]
        if rng.random() < cfg.by_system("p_email_missing", system):
            email = None
        line, city, postal = _fmt_address(rng, system, person["address"])
        mean_balance = 80_000 if system == "loans" else 12_000
        rec = {
            "system": system,
            "record_key": key,
            "person_id": person["person_id"],
            "open_month": month,
            "id_status": id_status,
            "seen": dict(person["ver"]),
            "state": {
                "first_name": first.upper() if system == "loans" else first,
                "middle_name": (middle.upper() if system == "loans" else middle) if middle else None,
                "surname": surname,
                "national_id": nid,
                "dob": dob.isoformat(),
                "phone": _fmt_phone(rng, system, phone) if phone else None,
                "email": _fmt_email(rng, system, email),
                "address_line": line,
                "city": city,
                "postal_code": postal,
                "balance": round(float(rng.lognormal(np.log(mean_balance), 0.9)), 2),
            },
        }
        self.records[key] = rec
        self.records_of[person["person_id"]].append(key)
        return key

    def schedule(self, person: dict, group: str, month: int, value) -> None:
        """A truth change reaches each existing record after a system-specific lag, or never."""
        for key in self.records_of[person["person_id"]]:
            system = self.records[key]["system"]
            never, mean = self.cfg.lag(group, system)
            if self.rng.random() < never:
                continue
            lag = int(self.rng.geometric(1.0 / (1.0 + mean))) - 1
            if month + lag <= N_MONTHS:
                self.pending[month + lag].append((key, group, person["ver"][group], value))

    def apply(self, key: str, group: str, seq: int, value) -> bool:
        rec = self.records[key]
        if seq <= rec["seen"][group]:
            return False  # an older change arriving after a newer one is ignored
        rec["seen"][group] = seq
        system, st, rng = rec["system"], rec["state"], self.rng
        if group == "address":
            st["address_line"], st["city"], st["postal_code"] = _fmt_address(rng, system, value)
        elif group == "phone":
            st["phone"] = _fmt_phone(rng, system, value)
        elif group == "surname":
            st["surname"] = _fmt_surname(rng, system, value)
        elif group == "email":
            st["email"] = _fmt_email(rng, system, value)
        return True


def _plan_products(rng: np.random.Generator, cfg: WorldConfig, people: list[dict]):
    """(month, system, person_id) openings, including within-system duplicates."""
    openings = []
    for p in people:
        r = rng.random()
        kind = "both" if r < cfg.p_both else ("loans" if r < cfg.p_both + cfg.p_loans_only else "cards")
        first_month = 1 if rng.random() < cfg.p_legacy else int(rng.integers(2, N_MONTHS + 1))
        if kind == "both":
            first_sys = "loans" if rng.random() < 0.55 else "cards"
            second_sys = "cards" if first_sys == "loans" else "loans"
            second_month = first_month
            if first_month < N_MONTHS and rng.random() < cfg.p_second_product_later:
                second_month = int(rng.integers(first_month + 1, N_MONTHS + 1))
            openings += [(first_month, first_sys, p["person_id"]), (second_month, second_sys, p["person_id"])]
        else:
            openings.append((first_month, kind, p["person_id"]))
    duplicates = []
    for month, system, pid in openings:
        if month < N_MONTHS and rng.random() < cfg.by_system("p_duplicate", system):
            duplicates.append((int(rng.integers(month + 1, N_MONTHS + 1)), system, pid))
    return openings + duplicates


def _life_events(sim: _Systems, month: int) -> None:
    rng, cfg = sim.rng, sim.cfg
    for members in sim.households.values():
        if rng.random() < cfg.p_move:
            address = _random_address(rng)
            for p in members:
                p["address"] = address
                p["ver"]["address"] += 1
                sim.schedule(p, "address", month, address)
    for p in sim.people:
        if rng.random() < cfg.p_phone_change:
            p["phone"] = sim.population.phone()
            p["ver"]["phone"] += 1
            sim.schedule(p, "phone", month, p["phone"])
        if p["email"] is not None and rng.random() < cfg.p_email_change:
            p["email"] = p["email"].split("@")[0] + "@" + ref.EMAIL_DOMAINS[int(rng.integers(6))]
            p["ver"]["email"] += 1
            sim.schedule(p, "email", month, p["email"])
        age = 2024 - p["dob"].year
        if (p["gender"] == "F" and 22 <= age <= 45 and p["ver"]["surname"] == 0
                and rng.random() < cfg.p_marriage):
            new = sim.population.surname()
            p["surname"] = f"{p['surname']}-{new}" if rng.random() < 0.2 else new
            p["ver"]["surname"] += 1
            sim.schedule(p, "surname", month, p["surname"])


def _remediate(sim: _Systems) -> set[str]:
    rng, cfg, changed = sim.rng, sim.cfg, set()
    for key, rec in sim.records.items():
        if rec["id_status"] == "typo" and rng.random() < cfg.p_fix_id_typo:
            rec["state"]["national_id"] = sim.by_pid[rec["person_id"]]["national_id"]
            rec["id_status"] = "ok"
            changed.add(key)
        elif rec["id_status"] == "missing" and rec["system"] == "cards" and rng.random() < cfg.p_backfill_id:
            nid = sim.by_pid[rec["person_id"]]["national_id"]
            typo = rng.random() < cfg.by_system("p_id_typo", "cards")
            rec["state"]["national_id"] = _id_typo(rng, nid) if typo else nid
            rec["id_status"] = "typo" if typo else "ok"
            changed.add(key)
    return changed


@dataclass
class World:
    versions: pd.DataFrame
    links: pd.DataFrame
    people: pd.DataFrame
    config: WorldConfig
    seed: int

    def save(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.versions.to_parquet(root / "versions.parquet", index=False)
        self.links.to_parquet(root / "links.parquet", index=False)
        self.people.to_parquet(root / "people.parquet", index=False)
        manifest = {"seed": self.seed, "people": len(self.people), "months": N_MONTHS,
                    "config": asdict(self.config)}
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2))


def generate(n_people: int = 10_000, seed: int = 7, cfg: WorldConfig | None = None) -> World:
    cfg = cfg or WorldConfig()
    rng = np.random.default_rng(seed)
    population = _Population(rng, cfg)
    people = population.build(n_people)
    sim = _Systems(rng, cfg, population)
    openings = defaultdict(list)
    for month, system, pid in _plan_products(rng, cfg, people):
        openings[month].append((system, pid))

    rows = []
    for month in range(1, N_MONTHS + 1):
        if month > 1:
            _life_events(sim, month)
        changed: set[str] = set()
        todays = openings[month]
        for i in rng.permutation(len(todays)):
            system, pid = todays[i]
            changed.add(sim.capture(system, sim.by_pid[pid], month))
        for key, group, seq, value in sim.pending.pop(month, []):
            if sim.apply(key, group, seq, value):
                changed.add(key)
        changed |= _remediate(sim)
        for key in sorted(changed):
            rec = sim.records[key]
            rows.append({"system": rec["system"], "record_key": key, "load_month": month, **rec["state"]})

    versions = pd.DataFrame(rows, columns=VERSION_COLUMNS)
    links = pd.DataFrame(
        [(k, r["person_id"], r["system"], r["open_month"]) for k, r in sim.records.items()],
        columns=["record_key", "person_id", "system", "open_month"],
    )
    people_df = pd.DataFrame([
        {"person_id": p["person_id"], "household_id": p["household_id"], "gender": p["gender"],
         "dob": p["dob"].isoformat(), "national_id": p["national_id"], "twin_of": p["twin_of"],
         "junior_of": p["junior_of"]}
        for p in people
    ])
    return World(versions, links, people_df, cfg, seed)


def snapshot(versions: pd.DataFrame, month: int) -> pd.DataFrame:
    """What each source system held at the end of ``month``: the latest version of every record."""
    upto = versions[versions["load_month"] <= month]
    latest = upto.sort_values(["record_key", "load_month"]).drop_duplicates("record_key", keep="last")
    return latest.reset_index(drop=True)


def load(root: Path) -> World:
    manifest = json.loads((root / "manifest.json").read_text())
    cfg_raw = manifest["config"]
    cfg = WorldConfig(**{k: tuple(tuple(x) for x in v) if isinstance(v, list) else v
                         for k, v in cfg_raw.items()})
    return World(
        pd.read_parquet(root / "versions.parquet"),
        pd.read_parquet(root / "links.parquet"),
        pd.read_parquet(root / "people.parquet"),
        cfg,
        manifest["seed"],
    )
