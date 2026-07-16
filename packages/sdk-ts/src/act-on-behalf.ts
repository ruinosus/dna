/**
 * `act-on-behalf` — the provider-agnostic "act on behalf of the user" contract.
 *
 * The TypeScript parity twin of `dna_cli.act_on_behalf._port` (Python). Feature
 * `f-act-on-behalf-port` (ADR-act-on-behalf-port §4), under epic
 * `e-dna-portability`.
 *
 * This is the **surface only** — for the PoC, execution stays Python-side (the MCP
 * server is Python; ADR §8). What must stay parity-identical is the *contract*: the
 * shape of `ActContext` / `UserCredential` / `ActOnBehalfPort`, in camelCase.
 *
 * The abstraction splits the flow into two steps and abstracts only the first:
 *
 *   (A) acquire a user-scoped credential      ← PROVIDER-SPECIFIC (OBO / OAuth / DWD)
 *   (B) call "the calendar API" as that user  ← COMMON, per-capability adapter
 *
 * `ActOnBehalfPort` is step (A). A capability adapter (step B) consumes the returned
 * `UserCredential` and never sees whether it came from a Microsoft OBO exchange, a
 * Google OAuth refresh, or a DWD-impersonated token.
 *
 * Security posture — inherited verbatim from the Microsoft OBO reference impl: a
 * `UserCredential` is request-lifetime only; it is never persisted, never logged,
 * and never returned to the MCP client.
 */

/**
 * The verified inbound request, provider-neutral (ADR §4.2).
 *
 * `rawToken` is **optional** and that is the whole point: the Microsoft OBO exchange
 * needs the inbound bearer as its `assertion`; Google auth-code/DWD do NOT. The port
 * abstracts the *outcome*, not Microsoft's *mechanism*, so each impl takes only what
 * it needs (the Python twin's `ActContext.raw_token: str | None`).
 */
export interface ActContext {
  /** Which provider family this identity maps to (`"microsoft"` / `"google"`). */
  readonly providerHint: string;
  /** The resolved DNA tenant/workspace (already computed by the tenancy bridge). */
  readonly tenant: string;
  /** The principal to act as — the user's durable id / email. */
  readonly subject: string;
  /** The inbound bearer. Microsoft OBO needs it as the `assertion`; Google does not. */
  readonly rawToken?: string | null;
  /** The verified claims, for providers that need more (e.g. Entra `tid`). */
  readonly claims: Record<string, unknown>;
}

/**
 * The common output of step (A): a bearer + the base URL of the provider's API.
 *
 * A capability adapter (step B) uses ONLY this — it never sees OBO vs OAuth vs DWD.
 * Request-lifetime only: never persisted, never logged, never returned to the client.
 */
export interface UserCredential {
  /** The user-scoped access token for the outbound API request. Never surfaced back. */
  readonly bearer: string;
  /** The provider API root (`graph.microsoft.com` | `www.googleapis.com`). */
  readonly apiBase: string;
  /** Unix epoch seconds when `bearer` expires (0 when the provider does not report it). */
  readonly expiresAt: number;
}

/**
 * Provider-agnostic "act on behalf of the user" — step (A) of the flow.
 *
 * Each provider implements this its own way behind one contract:
 * - Microsoft → OBO exchange (assertion = `ctx.rawToken`) → Graph token.
 * - Google → the user's consented OAuth token / a DWD-impersonated token
 *   (`sub = ctx.subject`); needs no `rawToken`.
 */
export interface ActOnBehalfPort {
  /** The provider-family this impl serves (`"microsoft"` | `"google"`). */
  readonly provider: string;

  /** Does this provider+deployment offer `capability` (calendar/files/mail)? */
  supports(capability: string): boolean;

  /**
   * Return a user-scoped credential for `capability` at least-privilege `scopes`.
   * THE provider-specific step. Throws {@link ActOnBehalfUnavailable} when this
   * identity cannot be acted upon.
   */
  credentialFor(
    ctx: ActContext,
    capability: string,
    scopes: string[],
  ): Promise<UserCredential>;
}

/**
 * This identity cannot be acted upon for the requested capability.
 *
 * The honest capability-gap signal (ADR §4.3) — e.g. a non-Entra identity asking the
 * Microsoft impl (no inbound assertion to exchange), a provider that does not offer
 * the capability, or a deployment where the provider is off. A structural, testable
 * branch, NOT a masked failure. Carries no token/secret by construction.
 */
export class ActOnBehalfUnavailable extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ActOnBehalfUnavailable";
  }
}
