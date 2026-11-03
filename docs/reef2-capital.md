# Apex capital competition (policy C1)

Two active pods start with $3,000 each and a $4,000 central reserve. Every 10 sessions, beginning once each pod has 15 marked sessions, Apex reviews them and may move one small step of capital toward the winner. Deterministic, no model, $0. The numbers are starting rules, not tuned parameters; all are in `the_reef/allocation/capital.py::CapitalPolicy` and are copied into every decision.

## The rules, in order
1. **Trust.** If any holding could not be marked at the close, nothing moves.
2. **History.** A pod is judged only after 15 marked sessions; fewer than two judged pods means hold.
3. **Score.** Return over the last 20 sessions minus half its worst drawdown in that window, both time-weighted so transfers are removed.
4. **Winner.** The higher score leads. A gap under 2 points is a draw (4 points to reverse the previous transfer, which limits oscillation). A leader whose own score is not positive is not rewarded.
5. **Quality.** The leader must have made at least 3 proposals in the window. A proposal is a `PROPOSAL_SUBMITTED` event: what Apex was shown. Signals withheld as untradable (`OPPORTUNITY_SUPPRESSED`, see [selection](reef2-selection.md)) are not proposals and do not count; the threshold is unchanged.
6. **Transfer.** One step of 5% of fund NAV (about $500, whole $10): first from the trailer's uncommitted cash (never below half its initial funding, never cash promised to a queued order), then from the reserve (which keeps 10%). The leader never exceeds 50% of the fund. No position is ever sold to fund a transfer.

## Accounting
- A review is one `APEX_CAPITAL_DECISION` event (evidence, rationale, time, ordered transfers; moves no money) followed by signed `SLEEVE_FUNDED` events with `ref=review-NNN`, reclaims first. Re-running a session never recomputes a recorded decision and appends only the transfers still missing, so a crash between events resumes exactly.
- The ledger refuses to defund cash committed to queued orders. Fund NAV, realized P&L and positions are unchanged by a transfer.
- Performance is time-weighted: a transfer after one close joins the base of the next session's return, so receiving $500 is never a return. `funded + realized + unrealized = NAV` still holds, with `funded` the net capital contributed.
- `verify_capital` (Python) and `verifyCapital` (Research Lab, in the browser) re-check every review from events alone.

## What the demonstration shows
Same synthetic prices as before. Momentum leads at reviews 15 and 25 and is paid $500 and $510 from Contrarian's idle cash. Review 35 holds with `LEADER_CANNOT_DEPLOY`: with untradable signals no longer counted, Momentum made 2 proposals in the window, under the required 3 (before the eligibility correction the withheld DEAL signals padded the count to 11 and the review moved a further $510). Reviews 45, 55 and 65 hold: the race is too close. [Before/after report](reef2-utilization-report.md). Extra capital raises capacity, not deployment: the Risk Engine's position cap and D0's one new position per session still bound what Momentum can put to work, and those were not changed.
