"""The risk taxonomy — 15 CUAD clause types built deep.

Each entry pairs a CUAD clause label (EXACT string — gold matching is case- and
string-sensitive) with: a *definition* (what the extractor looks for), a *default
severity*, and a *plain-English risk note* (the "why this is risky" a reviewer
reads). One domain (commercial-contract red flags), built carefully — every type
gets equal care, a unit test, and a fixture.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Clause:
    name: str          # EXACT CUAD label
    severity: str      # default severity: high | medium | low
    definition: str    # what to look for (drives the extraction prompt)
    risk_note: str     # plain-English why-this-is-risky (shown to the reviewer)


# Ordered roughly by typical deal-risk salience.
CLAUSES: dict[str, Clause] = {
    "Uncapped Liability": Clause(
        "Uncapped Liability", "high",
        "Language stating that a party's liability is NOT limited, that the liability cap does "
        "not apply, or carve-outs (indemnity, IP infringement, confidentiality, gross negligence) "
        "that are expressly excluded from any cap on damages.",
        "Exposure is unlimited — a single breach in a carved-out category can exceed the entire "
        "contract value. This is the single largest financial risk a reviewer can miss.",
    ),
    "Cap On Liability": Clause(
        "Cap On Liability", "high",
        "A clause that limits the maximum aggregate liability of a party (e.g. 'liability shall "
        "not exceed the fees paid in the prior 12 months', or a fixed dollar cap).",
        "Caps how much you can recover if the counterparty fails. A low cap (or fees-paid cap) can "
        "leave you under-compensated for a serious breach — confirm the cap matches your exposure.",
    ),
    "Liquidated Damages": Clause(
        "Liquidated Damages", "high",
        "A pre-agreed fixed sum or formula payable on breach/termination/delay, independent of "
        "actual proven damages (often 'as liquidated damages and not as a penalty').",
        "Fixes your downside in advance regardless of real harm — it can vastly over- or "
        "under-state damages and may be unenforceable if it reads as a penalty.",
    ),
    "Renewal Term": Clause(
        "Renewal Term", "medium",
        "Provisions on how the contract renews — especially AUTOMATIC renewal / evergreen terms "
        "that extend the agreement unless a party gives notice within a window.",
        "Auto-renewal locks you into another full term if you miss the (often short) notice window "
        "— a classic way costs and commitments quietly persist past their intended end.",
    ),
    "Non-Compete": Clause(
        "Non-Compete", "high",
        "A restriction barring a party (or its principals) from competing, operating a competing "
        "business, or working in a defined market/territory for a period.",
        "Limits your freedom to operate or hire — overbroad scope, geography, or duration can "
        "foreclose whole lines of business and may be unenforceable in some jurisdictions.",
    ),
    "Exclusivity": Clause(
        "Exclusivity", "high",
        "A clause granting exclusive rights / requiring a party to deal only with the counterparty "
        "(exclusive supplier, distributor, territory, or customer).",
        "Forecloses alternatives — you cannot source, sell, or partner elsewhere even if the "
        "counterparty underperforms, concentrating dependency and pricing power with them.",
    ),
    "No-Solicit Of Employees": Clause(
        "No-Solicit Of Employees", "medium",
        "A clause prohibiting a party from soliciting, hiring, or poaching the other party's "
        "employees (or contractors) during and after the term.",
        "Restricts your hiring — a broad no-hire (vs. no-solicit) can block legitimate recruiting "
        "of people who approach you on their own, and can outlast the deal.",
    ),
    "Most Favored Nation": Clause(
        "Most Favored Nation", "high",
        "A guarantee that a party gets terms (usually price) at least as favorable as those the "
        "counterparty offers any other customer/partner — an MFN / most-favored-customer clause.",
        "Forces you to extend your best terms automatically and can cap your pricing flexibility "
        "across all deals; auditing and enforcing MFN compliance is operationally costly.",
    ),
    "Ip Ownership Assignment": Clause(
        "Ip Ownership Assignment", "high",
        "A clause assigning ownership of intellectual property (inventions, work product, "
        "deliverables, derivatives) created under the agreement to one party.",
        "Determines who owns what you build. An assignment to the counterparty can strip you of "
        "rights to your own work product, background IP, or improvements — often irreversibly.",
    ),
    "License Grant": Clause(
        "License Grant", "medium",
        "A grant of a license to use IP/technology/marks, including its scope (exclusive vs. "
        "non-exclusive, field, territory, sublicensing, perpetuity).",
        "The scope of what each side may use. Overbroad, perpetual, or sublicensable grants can "
        "give away far more than intended; narrow grants can starve your own product needs.",
    ),
    "Termination For Convenience": Clause(
        "Termination For Convenience", "high",
        "A right to terminate the agreement for any reason (without cause) on notice, by one or "
        "both parties.",
        "The counterparty can walk away at will on short notice — undermining revenue certainty, "
        "investment recovery, and any volume or exclusivity commitments you relied on.",
    ),
    "Anti-Assignment": Clause(
        "Anti-Assignment", "medium",
        "A restriction on assigning or transferring the agreement (or rights/obligations under it), "
        "often requiring the other party's prior written consent.",
        "Can block a sale, financing, or reorganization — a change of control or asset sale may "
        "need counterparty consent, handing them leverage at your most vulnerable moment.",
    ),
    "Change Of Control": Clause(
        "Change Of Control", "high",
        "A provision triggered by a change in ownership/control of a party (merger, acquisition, "
        "majority-stake sale) — often a termination right or consent requirement.",
        "An acquisition can trigger termination or counterparty consent rights, jeopardizing key "
        "contracts exactly when an M&A deal depends on them — a frequent diligence killer.",
    ),
    "Source Code Escrow": Clause(
        "Source Code Escrow", "medium",
        "An obligation to deposit software source code with a third-party escrow agent, released "
        "to the licensee on defined trigger events (vendor bankruptcy, end-of-support).",
        "Governs your continuity if the vendor fails. Missing or weak escrow/release triggers can "
        "leave you unable to maintain critical software when the vendor disappears.",
    ),
    "Audit Rights": Clause(
        "Audit Rights", "medium",
        "A right for one party to audit/inspect the other's records, books, facilities, or usage "
        "to verify compliance (royalties, usage limits, payments).",
        "Imposes inspection and compliance burden — broad audit rights mean cost, disruption, and "
        "exposure of your records; absent rights mean you cannot verify what you are owed.",
    ),
}

# Stable ordered list of the exact CUAD labels.
RISK_TYPES: list[str] = list(CLAUSES.keys())


def extraction_taxonomy_block() -> str:
    """Render the taxonomy as a numbered definition block for the extractor prompt."""
    lines = []
    for i, (name, c) in enumerate(CLAUSES.items(), 1):
        lines.append(f"{i}. {name} — {c.definition}")
    return "\n".join(lines)
