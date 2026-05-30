Task 1: Product Scoping — Marketing Signal Dashboard
What I Built and Why
I scoped an internal marketing performance tool called the Marketing Signal Dashboard (MSD).
The core question the team has is: "How is our marketing performing across channels right now, and where should we be focusing?" I treated this as a literal product brief and worked backwards from it.
Key Decisions I Made
1. Internal-only in v1, not client-facing
The temptation is to build for both. I chose internal-only because the trust requirements for clients are fundamentally different — they need context, explanation, and polish. Building for two audiences at once means building for neither well.
2. Nightly data pull, not live API calls
Live calls on page load feel more impressive but create real problems: latency, rate limits, failures during demos. A nightly pipeline that lands data in BigQuery and serves the frontend from views is slower to update but dramatically more reliable.
3. A "Focus Signal" instead of raw data
The question is "where should we be focusing?" — not just "show me the numbers." I added a single derived callout that surfaces the most over- or under-performing channel relative to its 4-week baseline. This turns data into a decision signal.
4. Explicit trust design
I spent deliberate time on what makes an analyst trust a tool. The answer: honesty about limits — stale data warnings, broken connection states, and marking derived metrics as derived.
5. A firm v1 exclusion list with reasoning
I ruled out: client portal, AI recommendations, cross-brand aggregation, mobile layout, campaign drill-down, and forecasting. Each exclusion has a specific reason. Scope discipline is as important as what you include.
What I Would Revisit With More Time

Validate the Focus Signal baseline algorithm with the team before shipping
Design the v2 client access pathway now, even before building it
Instrument usage patterns from day one

Files in This Folder

PRODUCT_BRIEF.md — Full product brief
wireframe.html — Interactive wireframe (open in browser)
README.md — This file

The One Thing I Want You to Take Away
The simplest version that is genuinely useful is a dashboard that shows one row per channel, five numbers, and a trend arrow, for a selected brand, for the last 7 days. That is the product. Everything else is a feature.
