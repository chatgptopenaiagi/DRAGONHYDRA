# Bundled examples and public football inputs

The synthetic JSON files are explicitly labelled deterministic research examples.
The two OpenFootball JSON files are retained public fixtures/results captured in
2026. Original source URLs, capture times, byte counts and SHA-256 values remain
in their matching receipt files. Importing them now establishes local knowledge
now; a fixture date is not a historical availability timestamp.

OpenFootball football.json: <https://github.com/openfootball/football.json>.
Data is published under CC0-1.0. The files are not a live stream. Team identities
and tables are source-scoped; reconstructed standings are not official tables.

The Football-Data.co.uk 2025/26 CSV is retained for the existing archive CLI.
Attribution and source notes: <https://www.football-data.co.uk/>,
<https://www.football-data.co.uk/notes.txt>, and
<https://www.football-data.co.uk/contact.php>. Original receipt and bytes remain
together. Bookmaker column labels are source claims, not verified independent
feeds; quote timestamps and contemporaneous executable prices are unknown.

Dashboard resources mirror client/desktop/web exactly. The release gate compares
their hashes before building, so the wheel and frozen server ship the same UI.
