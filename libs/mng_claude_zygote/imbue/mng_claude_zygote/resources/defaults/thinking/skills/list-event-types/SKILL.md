
Event sources:

- **messages**: A user or agent posted in a conversation thread. Includes `conversation_id`, `role`, and `content`.
- **scheduled**: A scheduled trigger fired. Process according to the event's `data` payload.
- **mng_agents**: A sub-agent changed state (finished, blocked, crashed). Review its work, clean it up, or retry as needed.
- **stop**: You are about to stop. This is your last chance to check for unprocessed work before sleeping.
