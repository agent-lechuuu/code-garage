"""Licence and trust policy for the whole repo: check(catalog, pins, trust) -> [error strings] (empty = fine).

Called by `garage validate` (T1) and CI on every PR. Rules (research/system-design.md sections 3 and 4):
  1. `use: vendor|template` (code copied into a project or our repo) only under a licence that allows it: never GPL,
     AGPL, LGPL, no licence, NOASSERTION/other, source-available/proprietary, BUSL, SSPL, FSL, Elastic, Commons Clause,
     PolyForm, or CC-*-NC*. The pin's license_at_pin counts first; the catalog's licence when GitHub saw none.
  2. The never-vendor list: Semgrep rules (licence forbids redistribution), HackTricks (CC-BY-NC), Anthropic's
     source-available document skills (docx, pdf, pptx, xlsx): never vendor/template and never trusted (trusted items
     are what gets copied into plugins/packs).
  3. Trust records: valid shape; only for runnable catalog resources; `trusted` needs approved_by: owner + an approval
     id; `reviewed`/`trusted` need a review record; a record's sha must equal the pin's sha (a pin bump must reset the
     record to quarantine: garage.trust.reset) and an item can't be reviewed/trusted without a pin.
  4. A reviewed/trusted record whose scans include a fail needs a waiver (with a reason) for that tool.
"""
import re

from . import trust as trust_mod

BAD_LICENCE = [
    (re.compile(r"(^|[^a-z])(a|l)?gpl", re.I), "copyleft (GPL/LGPL/AGPL): reference or run as a separate process only"),
    (re.compile(r"^(none|noassertion|other|unknown|unlicensed|no[ -]?licen[cs]e|)$", re.I),
     "no licence / NOASSERTION: link only until a person reads the licence"),
    (re.compile(r"source[- ]available|proprietary|all rights reserved|licenseref|custom|commercial", re.I),
     "source-available / proprietary terms"),
    (re.compile(r"busl|business source", re.I), "BUSL (source-available until the change date)"),
    (re.compile(r"sspl|server side public", re.I), "SSPL"),
    (re.compile(r"(^|[^a-z])fsl|functional source", re.I), "FSL (source-available)"),
    (re.compile(r"elastic|elv2", re.I), "Elastic License (source-available)"),
    (re.compile(r"commons[- ]clause", re.I), "Commons Clause (no selling)"),
    (re.compile(r"polyform", re.I), "PolyForm (source-available)"),
    (re.compile(r"cc-by(-sa)?-nc|cc-by-nc|-nc-|-nc$|noncommercial|non-commercial", re.I), "Creative Commons NonCommercial"),
]

# (pattern on the rid, why). Matched against the normalised URL.
NEVER_VENDOR = [
    (re.compile(r"^https://github\.com/(semgrep|returntocorp)/(semgrep-rules|skills)(/|$)", re.I),
     "Semgrep Rules License: internal use only, no redistribution"),
    (re.compile(r"^https://(github\.com/(hacktricks-wiki|carlospolop)/hacktricks(-cloud)?|book\.hacktricks\.(wiki|xyz)"
                r"|cloud\.hacktricks\.(wiki|xyz)|(www\.)?hacktricks\.(wiki|xyz))(/|$)", re.I),
     "HackTricks: CC-BY-NC-4.0, no commercial reuse"),
    (re.compile(r"^https://github\.com/anthropics/skills/(tree|blob)/[^/]+/(skills/|document-skills/)?(docx|pdf|pptx|xlsx)"
                r"(/|$)", re.I),
     "Anthropic document skills: source-available, all rights reserved"),
]

VENDOR_USES = {"vendor", "template"}


def licence_problem(lic):
    lic = str(lic if lic is not None else "").strip()
    for pat, why in BAD_LICENCE:
        if pat.search(lic):
            return why
    return None


def never_vendor(rid):
    for pat, why in NEVER_VENDOR:
        if pat.search(rid):
            return why
    return None


def _licence(res, pin):
    try:
        from .pins import effective_license
        return effective_license((pin or {}).get("license_at_pin"), res.get("license"))
    except ImportError:
        g = str((pin or {}).get("license_at_pin") or "")
        return g if g.lower() not in ("", "none", "noassertion", "other") else str(res.get("license") or g or "none")


def check(catalog, pins, trust):
    pins = pins or {}
    trust = trust or {}
    resources = (catalog or {}).get("resources") or {}
    errors = []
    for rid, res in sorted(resources.items()):
        pin = pins.get(rid)
        nv = never_vendor(rid)
        if res.get("use") in VENDOR_USES:
            if nv:
                errors.append(f"{rid}: use {res['use']} refused: {nv}")
            else:
                lic = _licence(res, pin)
                why = licence_problem(lic)
                if why:
                    errors.append(f"{rid}: use {res['use']} refused under licence {lic or 'none'}: {why}")
    if not isinstance(trust, dict):
        return errors + ["trust/registry.yaml: not a mapping"]
    errors += trust_mod.validate(trust)
    for rid, rec in sorted(trust.items()):
        if not isinstance(rec, dict):
            continue
        rec = trust_mod._norm(rec)
        t = rec.get("trust")
        res = resources.get(rid)
        if res is None:
            errors.append(f"{rid}: trust record for a resource that isn't in the catalog")
        elif not trust_mod.is_runnable(res):
            errors.append(f"{rid}: trust record for a resource that isn't runnable (use {res.get('use')}, "
                          f"kind {res.get('kind')})")
        if t in ("reviewed", "trusted"):
            pin = pins.get(rid)
            if not pin:
                errors.append(f"{rid}: {t} but not pinned in lock/pins.yaml")
            elif pin.get("sha") != rec.get("sha"):
                errors.append(f"{rid}: {t} record is for {str(rec.get('sha'))[:12]} but the pin is "
                              f"{str(pin.get('sha'))[:12]}: re-review, or reset the record to quarantine with the bump")
            waived = {str(w.get("tool")) for w in rec.get("waivers") or [] if isinstance(w, dict)}
            for s in rec.get("scans") or []:
                if isinstance(s, dict) and s.get("result") == "fail" and s.get("tool") not in waived:
                    errors.append(f"{rid}: {t} although {s.get('tool')} failed and no waiver says why")
                if isinstance(s, dict) and s.get("result") in ("skipped", "error") and s.get("tool") in \
                        ("skillspector", "garage-checks"):
                    errors.append(f"{rid}: {t} although the required scanner {s.get('tool')} did not run")
        if t == "trusted":
            nv = never_vendor(rid)
            if nv:
                errors.append(f"{rid}: can't be trusted (trusted items are shipped in packs): {nv}")
    return errors


def health():
    try:
        from . import catalog, pins
        errs = check(catalog.load(), pins.all(), trust_mod.load())
    except Exception as e:   # noqa: BLE001 - doctor reports, never raises
        return [("WAIT", f"policy: not checked ({e})")]
    if errs:
        return [("FAIL", f"policy: {len(errs)} errors, first: {errs[0]}")]
    return [("PASS", "policy: licences and trust records ok")]
