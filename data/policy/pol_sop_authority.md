# SOP-001 · Refund & Replacement Authority Matrix v1.0
# Effective: 2024-01-01 | Owner: Support Operations

## Purpose

This Standard Operating Procedure defines which organisational roles are
authorised to approve customer refund and replacement requests, and within
what monetary limits. The policy engine enforces these limits programmatically
— no human can override a tier restriction without a database-level escalation.

## Authority Tiers

| Tier | Role | Refund / Replacement Limit | Target SLA |
|------|------|---------------------------|------------|
| 1 | Support Agent | Up to $25.00 | Auto-approved immediately |
| 2 | Senior Support Agent | $25.01 – $100.00 | Same business hour |
| 3 | Team Supervisor | $100.01 – $250.00 | Within 4 business hours |
| 4 | Operations Manager | $250.01 – $750.00 | Next business day |
| 5 | Director / Finance | Above $750.00 | Dual sign-off required |

## Rules

1. **Auto-approve (Tier 1):** The system automatically processes refunds and
   replacements ≤ $25.00 without human review. These are logged with
   actor = "system:auto".

2. **Tier 2–5 approvals:** The system creates a pending SopApproval record and
   notifies the customer that the request is under review. The approver must
   select their role in the Ops Console; the system rejects an approval if
   the selected role does not meet the required tier.

3. **Cascading authority:** A higher-tier authority may approve any request
   within a lower tier (e.g. a Supervisor can approve a Tier 2 request).

4. **Denial:** Any tier may deny. Denial does not require a higher authority.

5. **Audit:** Every approval and denial writes an immutable AuditLog row
   containing the approver role, tier, correlation ID, and decision note.

6. **Exceptions:** Refunds flagged HIGH_RISK (> $500) or SUSPECTED_ABUSE
   (≥ 3 refunds in 30 days) bypass the SOP tier matrix and are routed
   directly to Director / Finance regardless of amount.

## Replacement-specific rules

Replacements are approved using the same tier matrix as refunds, based on
the replacement item's unit price. If the item is out of stock, the
replacement is automatically converted to a refund at the same tier.

## Review cadence

This SOP is reviewed quarterly by the Head of Support Operations. Version
history is maintained in git; each change requires two approvals.
