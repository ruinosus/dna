# Act on behalf of the user — one calendar tool, any provider

DNA's thesis is *author once, DNA operates your digital life in any AI client.* The
[On-Behalf-Of guide](mcp-obo.md) showed DNA reading the signed-in user's **Microsoft
365** calendar on their behalf. This guide is the next step: the same capability made
**provider-agnostic** through the `ActOnBehalfPort`, so "read my calendar" works the
same way whether the user signed in with Microsoft or Google — the model sees one
neutral `calendar_list` tool, and *which* backend runs is decided by *who signed in*.

The full design (and the ratified decisions) is
[ADR-act-on-behalf-port](https://github.com/ruinosus/dna/blob/main/docs/adr/ADR-act-on-behalf-port.md).
This is the how-it-fits-together tour.

> **Status: PoC.** The port, the Microsoft reference impl, the neutral `calendar_list`
> adapter, and a **stubbed** Google skeleton are shipped and tested against fakes. A
> live Google integration (real OAuth consent + refresh storage, or Domain-Wide
> Delegation) is deferred — it needs a Google Cloud project, not more code.

## The seam: two steps, one abstracted

"Read the user's calendar" splits into two steps, and the port abstracts only the
first:

```
  (A) acquire a user-scoped credential      ← PROVIDER-SPECIFIC (OBO / OAuth / DWD)
  (B) call "the calendar API" as that user  ← COMMON, one capability adapter
```

- **`ActOnBehalfPort`** is step (A): `credential_for(ctx, capability, scopes)` returns
  a `UserCredential` (a bearer + the provider's API base). Microsoft does this with an
  On-Behalf-Of token exchange; Google does it with a previously-consented OAuth refresh
  token. The mechanisms genuinely differ — the port abstracts the *outcome*, not
  Microsoft's *mechanism*.
- The **`calendar_list` capability adapter** is step (B): it consumes the
  `UserCredential` and never sees whether it came from OBO, OAuth, or DWD. It returns
  one **neutral** event shape (`{count, events:[{id, subject, start, end, location,
  organizer, web_link}]}`) whichever provider served it.

### The asymmetry that proves it

`ActContext.raw_token` — the inbound bearer — is **Optional**. Microsoft OBO *needs* it
(it is the exchange `assertion`); Google auth-code/DWD do **not** (they use a consented
refresh token or a self-signed service-account JWT). Honoring that asymmetry in the
contract is the concrete proof the port is not just "Microsoft OBO with a coat of
paint".

## Identity → provider

DNA does not ask you to sign in again to pick a provider. The provider that **verified
your token** *is* the provider DNA acts through. The pluggable IdP layer already routes
each token to its provider; the port adds one label — a **provider-family stamp**
(`entra → microsoft`, `google → google`) — and the neutral tool reads it to select the
right `ActOnBehalfPort`. A Microsoft-signed-in user hits the Microsoft impl; a
Google-signed-in user hits the Google impl. An identity that maps to no configured
provider gets an honest "not available for you", never a crash.

## Using it

The neutral tool is opt-in and gated exactly like the [OBO tools](mcp-obo.md): with the
`graph:` calendar group active it registers as **`calendar_list`**, alongside the
unchanged `ms_calendar_list` (now the Microsoft *binding/alias*).

```jsonc
// the model calls ONE tool, regardless of provider
{ "tool": "calendar_list", "arguments": { "top": 10 } }
```

- Signed in with Microsoft → the On-Behalf-Of exchange → Microsoft Graph.
- Signed in with Google (once wired) → the OAuth refresh exchange → Google Calendar.
- Either way, the same neutral events come back. `ms_calendar_list` still works for
  callers that want the explicit Microsoft binding.

## What's deferred

The PoC proves the *seam*, not a production Google integration. Deferred: the real
Google OAuth consent flow + refresh-token storage, Domain-Wide Delegation, the
`files` / `mail` capabilities and all write scopes, multi-provider fan-out (one user,
both providers, merged results), the full per-provider config surface, and production
credential hardening. The dependency for going live is the per-provider **trust setup**
(an Entra app + consent; a Google OAuth client / Workspace super-admin) — not more
plumbing.
