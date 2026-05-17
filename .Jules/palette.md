## 2025-05-14 - Add stateful confirmation for account reset
**Learning:** Destructive actions like account resets require a multi-step confirmation to prevent accidental data loss. Using FSM states to manage this confirmation ensures that the action is intentional and provides a clear "Cancel" path.
**Action:** Always implement a dedicated FSM state for destructive operations and ensure both "Confirm" and "Cancel" handlers are explicitly defined for that state.
