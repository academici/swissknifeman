# Agent loop sketch

1. Observe current goal, authority, and relevant evidence.
2. Choose the next useful action within resource and permission boundaries.
3. Execute via the harness; validate inputs and correlate outcomes with calls.
4. Evaluate progress, including uncertain effects before retrying writes.
5. Continue until the authorized result is complete or a real boundary requires a checkpoint.

Independent resource-isolated operations may run together; serialize conflicting/dependent
effects. A checkpoint does not require a fresh session when the current context still suffices.
