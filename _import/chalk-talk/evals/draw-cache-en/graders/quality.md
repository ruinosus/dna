---
type: llm
target: { source: file, path: lesson.json }
---
The recipe (JSON) explains a web cache to junior developers: it starts from loading a product page twice, shows a
request going to the cache, a miss going to the database and the answer copied into the cache, and a hit served
without the database. It has a value for the hit rate, used in an expression so the drawing changes with it, and the
numbers it shows are consistent. It has chapters (about four), short narration (`say`), a `learning` with a question
and a caveat naming what was simplified (expiry, invalidation…). Texts are English. Fail it if a fact is wrong.
