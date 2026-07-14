"""The instrument — the halftime 2H total is an in-play line nobody archives.

For NCAAB the dataset does not exist; we create it. Detect halftime, snapshot totals_h2 across
all books, grade the next morning. Append-only, immutable, idempotent, resumable, crash-safe.
If this doesn't run unattended for four months, nothing else matters.
"""
