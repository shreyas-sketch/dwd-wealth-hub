"""Growth layer: plans & entitlements, the single event table, the Runs ledger,
referral attribution and the commission ledger (spec v1.0 §4–5, v1.1 §10, §12.3).

Every collection here is append-friendly and keyed by the user's id as a string
(str(users._id)), so it survives the OTP-login migration unchanged.
"""
