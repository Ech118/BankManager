# Cross-partition requests

To ask another partition for something (or to propose a schema change), ADD a new file:

    docs/requests/YYYY-MM-DD-pX-to-pY-<short-slug>.md

Contents: what you need, why, the exact field or function, urgency.
The owner replies by ADDING a sibling file ending in `-response.md` and does the work
in their own directory. Never edit an existing request file (this is what keeps merges
conflict-free). Schema changes: additive = coordinator applies; breaking = all three
people must OK it in the request file (plan.txt 15.11).
