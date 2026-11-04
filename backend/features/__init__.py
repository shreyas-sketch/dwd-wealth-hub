"""One module per product feature. Each exposes `router` (mounted under /api) and, where it
runs on a schedule, `job_*` coroutines registered in jobs/registry.py."""
DISCLAIMER = ("Educational research made by software and AI, not investment advice. Crypto is unregulated in India, "
              "very volatile and can lose most of its value. Gains are taxed at 30% plus 1% TDS. Decide for yourself.")
