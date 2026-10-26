# MoneyCompass — Product

Lithuanian-first personal finance web app. People upload a bank statement themselves (no bank connection) and see where their money goes. Free for everyone. Detailed positioning lives in `.claude/product-marketing-context.md`.

## Who uses it
- Lithuanian adults, mostly on phones, who found us through search ("išlaidų sekimas", "asmeninis biudžetas").
- Not finance experts. They want one answer first: **where did my money go this month?**
- Privacy-minded: they like that we never log in to their bank.

## The job of the app, in order
1. **First visit:** make the first upload obvious and easy. One action, clear bank-by-bank instructions, no setup chores before value.
2. **After the first upload:** show this month's spending, income and what is left, then the biggest categories. Everything else is secondary.
3. **Return visits:** fix a few uncategorized rows, upload the next statement, glance at trends.

## Known funnel problem (2026-10)
Users register, activate, then leave before importing anything. Friction points found in code: setup popup + 4-step banner, "review categories" before upload, 30 manual labels before AI helps, only Revolut/SEB/Swedbank CSV supported, empty dashboard full of blank charts.

## Principles
- Value before work. Never ask for setup the user can do later.
- One primary action per screen.
- Plain Lithuanian, short sentences. Explain finance terms or avoid them.
- Calm: spending is not an error. Red only for real problems (over a limit, failed import).
- Every empty state says what to do next.
