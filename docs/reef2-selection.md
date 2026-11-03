# Opportunity selection: eligibility before ranking

## The defect
A strategy keeps its best `max_candidates` (2) signals, D0 funds the best `max_new_per_session` (1) of those, and only then does the execution gate ask whether the name can be bought. A name the gate will certainly refuse (a definitive cash acquisition is pending, so the price is pinned) could therefore rank first, take D0's only slot, be refused, and leave a tradable name behind it unfunded. On the 70-session fixture DEAL was declined by the gate on 21 Momentum sessions and one Contrarian session; on three of them (two for Momentum, one for Contrarian) a tradable name was left behind it unfunded.

## The correction
In `engine/advance.py::_screen_candidates`, before a pod's strategy proposes, the engine asks the gate's own rule (`execution/gate.py::screen_candidate`, which calls `check_tradable` through the same helper `queue_order` uses) whether an OPEN in each candidate name decided now would be accepted. Names that would not be are added to the strategy's `blocked` set, so the strategy ranks and truncates only names that can be bought. Nothing else about ranking changed: same scores, same `max_candidates`, same D0 slot, same sizing, same Risk Engine limits.

- **Point in time.** The check uses the decision time as the knowledge time, exactly as the gate does: a corporate action not yet public cannot suppress anything (tested to the microsecond). The instrument master and corporate-action source are the existing ports.
- **Backstops are untouched.** The gate still checks at the queue and again at the next open (`fill_at_open`); a name that becomes untradable between close and open is still refused at the fill and nothing trades at a stale price.
- **Scope.** Only new positions are screened. Held names are never suppressed, and exits are never screened or blocked.
- **Flag.** `EngineDeps.screen_untradable` (default `True`). `False` reproduces the old pipeline and exists so the diagnostic can run "before"; there is no reason to set it otherwise.

## The audit trail
Every signal the strategy would have produced for a withheld name is written to the ledger as `OPPORTUNITY_SUPPRESSED` (audit only, moves no money): pod, instrument, session, decision time, the gate's reason code, detail and evidence, and the strategy's score, reference price, stop, rationale and spec hash. The engine asks the strategy about the withheld names repeatedly until none remains, so a signal is never lost to the candidate cap. One event per pod, session and instrument; ids are derived from those, so a crash and resume rewrites nothing. The Research Lab's event explorer lists them.

## Is a withheld signal a proposal? Does it count for C1?
No. A proposal is what Apex is shown (`PROPOSAL_SUBMITTED`); a withheld signal is not shown to Apex and has no `APEX_DECISION`. C1's quality test counts proposals, so withheld signals do not count toward `min_proposals`. Before this change a pending-deal name was submitted, declined by the gate, and counted; Momentum's review-035 evidence read 11 proposals, most of them DEAL. After it reads 2 and the unchanged policy holds with `LEADER_CANNOT_DEPLOY`. That changes one capital transfer on this fixture. It is a consequence of cleaner evidence, not a policy change; no C1 value was touched.

## What did not change
`max_candidates`, D0's one slot, the pods' 50% capital request, position and risk limits, exposure limits, C1 values, strategies and their ranking. No top-ups, pyramiding, larger requests or extra slots. See [the generated report](reef2-utilization-report.md) for the measured before/after and `tools/utilization_diagnostic.py` to reproduce it offline.
