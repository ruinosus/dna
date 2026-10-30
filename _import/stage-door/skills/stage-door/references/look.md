# What the check points out

`scripts/build.mjs` prints `! to look at: …` (in the language asked) for what does not hold. These are facts, read from
the file: ask about each one first, with your bet, and never ask what the file already says.

| It says | What to ask (with your bet) |
|---|---|
| a stage **delivers nothing** (the last one and an optional one aside) | what exists after it — an output, not an activity |
| **no gate** | where someone decides the work goes on, and who |
| **nobody approves** a gate | which role approves it |
| a gate's approver **is not one of the roles** | which role that is (add it to `roles`) |
| a gate **says nothing about what must be ready** | the outputs (or required activities, or numbers) it checks |
| a phase **is an environment** (DEV, QA, PRD) | the real milestones; the environments become `where` |
| a phase **has no deliverable and no gate closes it** | what it delivers, or whether it is a phase at all |
| **no stage measures** the result | the starting number, the target and how it is measured; propose a closing stage that measures |
| a stage **is a ritual** | leave it out of the flow (say why) |
| **no stage is led** by a lane | what that lane does, or whether it belongs |
| a role **reads as a person** | the function the person has; the person can go in a lane's `sub` |
| a role **takes part in nothing** | where it takes part, or whether it belongs |
| a stage **receives something nothing before it delivers** | does it come from outside (`name:`), or which stage should deliver it? |
| a stage **receives something only delivered later** | the order of the stages, or where it really comes from |
| an output **nobody receives** (the last stage's, numbers and a gate's aside) | who it is for — or whether it is needed |
| a gate **says nothing about what comes out of it** | the decision and what was approved |

The last four only appear when the file describes inputs: a way that never says what stages receive is not asked
about the thread.

Lines starting with `✗` are not questions: the file breaks the format there (the line number says where). Fix them
yourself and run the check again before you show anything.
