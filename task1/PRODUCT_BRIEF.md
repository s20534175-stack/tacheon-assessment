Product Brief: Marketing Signal Dashboard (MSD)
Version: 1.0 (Scoped)
Author: Santhosh B
Context: Internal tool for a marketing technology company supporting multiple client brands
Date: May 2026

The Problem Worth Solving
Every week, someone on the team asks: "How is our marketing performing across channels right now, and where should we be focusing?"
Today, answering that question means:

Opening 4–6 different tools (GA4, Meta Ads, Google Ads, HubSpot, etc.)
Exporting CSVs manually
Stitching numbers together in a spreadsheet
Writing an email or Slack message summarising it
Repeating this every time someone asks

The answer looks different every time depending on who does it. It takes 45–90 minutes. And if that one analyst is out, the question just sits unanswered.
The core failure is not that the data is missing. It is that the team has no single, trusted place to look.

The One Question This Tool Must Answer

"How is our marketing performing across channels right now, and where should we be focusing?"

Everything in v1 should exist to serve this question. If a feature does not help answer it, it does not belong in v1.

Who Is This Tool For?
Primary User: Internal Analyst / Account Manager
The person who currently stitches the data together manually. They want to:

Stop being the bottleneck
Have a trusted source they can point clients to
Spend less time gathering, more time interpreting

Secondary User: Client (Read-only)
Some clients will eventually want access. But in v1, we are not building for clients. Here is why:

Clients have different trust thresholds — they need explanation, context, and polish before we expose raw numbers to them
Building for both users simultaneously means building for neither well
An internal tool that works well can be packaged for clients in v2

Decision: v1 is internal-only. A single shared login is acceptable for now.

What the Tool Does in v1
1. Channel Summary (Home Screen)
A single screen showing all active channels for a selected client brand with key metrics per channel: Spend, Impressions, Clicks, Conversions, Cost per conversion (derived), Week-over-week trend.
2. Focus Signal
One highlighted callout per brand: the channel most over- or under-performing relative to its recent baseline. This is the "where to focus" answer — derived from data, not left to interpretation.
3. Date Range Selector
Last 7 days (default), Last 30 days, Custom.
4. Brand Switcher
A dropdown to switch between client brands.

Where the Data Comes From
Data is pulled nightly via a scheduled pipeline — not live API calls on page load. This is deliberate: live calls mean latency, rate limits, and failures at the worst moment. Data lands in BigQuery. The frontend reads from BigQuery views only.

What Makes a User Trust This Tool
The tool must be honest about what it does not know:

If data has not refreshed, show the last refresh timestamp and a warning
If an API connection is broken, surface it explicitly
If a metric is derived, mark it as derived

Trust is built by being transparent about limits, not hiding them.

What Is Explicitly NOT in v1

Client-facing login — premature, clients need polish we cannot deliver yet
AI-generated recommendations — not enough historical data in week one
Automated alerts — validate core views first
Cross-brand aggregated view — clients have different goals, aggregating produces a number nobody owns
Budget forecasting — requires historical patterns we don't have yet
Mobile layout — internal tool, analysts are on laptops
Campaign-level drill-down — channel-level answers "where to focus"; campaign-level is "why" — a v2 question


What I Would Revisit With More Time

Validate the Focus Signal baseline algorithm with the team before shipping
Design the v2 client access pathway now — permissions architecture is hard to retrofit
Instrument usage patterns from day one to know when "nightly" becomes "not fast enough"


Success Criteria for v1

An analyst can answer "how is [brand] performing this week?" in under 60 seconds without opening any other tool
Data is never more than 24 hours stale without the tool saying so
A new team member can understand what they are looking at without being trained


This brief represents my thinking on what to build and why. The reasoning behind what I left out matters as much as what I included.
