# PRD — Fraud checks

Score every order before capture. Orders above 80 go to the hold queue; support reviews them.

- Risk score API: p95 under 150 ms
- Hold queue: filter by score, approve or cancel
- Alerts: Slack message when the queue passes 50 orders
