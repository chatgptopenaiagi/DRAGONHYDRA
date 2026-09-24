# Independent odds observation model

`web/odds.py:OddsObservation` is a frozen contract independent of any bookmaker API. Fields: observation_id, fixture_id, source_id, bookmaker, market_type, market_key, selection, line_value, decimal_odds, implied_probability, observed_at, available_at, event_at, expires_at, currency_if_relevant, market_status, source_url, source_hash, confidence, verification_state, updated_at, target_as_of_at and synthetic.

Market statuses: OPEN, SUSPENDED, CLOSED, UNKNOWN. Missing quotes never imply SUSPENDED. Verification states: CONFIRMED, CORROBORATED, UNCONFIRMED, STALE, CONFLICTING, REJECTED. h2h, totals and spreads are recognized; line markets require a finite line. All decimal prices must be finite and >1. Boolean values are not prices.

Functions implement implied probability (1 / decimal odds), overround (sum of implied probabilities −1), normalized market probabilities, absolute odds delta, percentage movement and elapsed seconds. Overround/normalization require at least two supplied prices; the caller must ensure those prices form one complete, contemporaneous, mutually exclusive market. No profitability claim or betting action follows from these calculations.

Quote identity includes fixture, source, bookmaker, market, selection, line and observed time. A different price/status at the same identity is conflicting; a later observation is movement, not automatically a conflict. Same-key duplicates are suppressed. Cross-source quote adjudication remains a future adapter responsibility.

All external records retain source ID/URL/type, retrieval time, byte hash, parser version, terms/license/robots state and confidence. Synthetic records retain separate generator provenance and are always visibly labelled. Confidence 1.0 on a synthetic quote describes generation provenance, not outcome confidence.

Temporal rule: aware observed_at ≤ available_at ≤ updated_at, no future captured update; model use requires all three ≤ target_as_of_at. Historical event dates never backdate availability. The SQL as-of reader also gates committed creation time and selects the newest eligible version for each fixture. Source date/time without a verified timezone stays in separate fields; event_at is null. Future leakage and exact boundary inclusion are tested.
