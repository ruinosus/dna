# What the check points out

`scripts/build.mjs` prints `! to look at: …`. Each is a finding to show and, when it is missing information, a question:

| It says | What to ask (with your bet) — or show as a finding |
|---|---|
| the **worst moment has no action** | who acts on it, and what changes? |
| a moment with **nobody behind it** | who answers when the customer does this — a person, a screen, a system? |
| a **wait or failure with no evidence** | what does the customer get while they wait (an email, a status)? — often the fix itself |
| a **promise with no owner** | who answers for it? |
| a **promise with no time** | within how long? |
| a **system in almost every moment** | if it stops, what does the customer see? |
| a **pain with no source** | where did it come from (an interview, a ticket, a survey)? |
| an **action with no owner** | who does it? |

Lines with `✗` are not questions: the file breaks the format there. Fix them and check again.
