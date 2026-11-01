# kind arch — how a system works

Chapters: **the scenario → the pieces → one request end to end → the failure → what changes.**

- **The scenario:** who uses it and what they want, in one line at the top.
- **The pieces:** 4–6 props (`computer`, `server`, `api-gateway`, `lock` for a login, `database`, `cache`, `queue`,
  `function`, `cluster`, `cloud`), each with its everyday name as the label. A `chain` places them in order, but its
  arrows carry no label: when what travels matters, place the props and link them.
- **One request end to end:** follow one request through the pieces with labelled arrows — `app -> api "token A" ->
  graph "token B"` — or a `note`. `animate` the piece that works hardest.
- **The failure:** a `switch` («the provider is down») and a `when` that draws what happens then — **without a
  switch or a when the build says «no failure drawn»**. To break a link, draw it twice, one for each state:

  ```
  when "1 - down":
    api -> graph "token B"
  when down:
    arrow 560,250 -> 740,250 color=#C8442C dashed
    text "✗" at 640,240 size=34 color=#C8442C
  ```
- **What changes:** the design decision that handles the failure (a timeout, a cache, a retry), in a `highlight`.

Common mistakes: every box of the real system (keep 4–6 pieces); product logos (use the generic props); arrows with
no label.
