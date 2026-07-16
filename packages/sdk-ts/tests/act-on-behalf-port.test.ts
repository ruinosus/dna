/**
 * Story `s-aob-port-contract` (TS parity) — the `ActOnBehalfPort` contract shape.
 *
 * The camelCase twin of `tests/test_act_on_behalf_port.py`. Shape tests only: a fake
 * provider satisfies the interface, `ActContext.rawToken` is optional (the Microsoft
 * ↔ Google asymmetry), and `ActOnBehalfUnavailable` is the honest capability gap.
 */
import { describe, expect, test } from "bun:test";
import {
  ActOnBehalfUnavailable,
  type ActContext,
  type ActOnBehalfPort,
  type UserCredential,
} from "../src/act-on-behalf.js";

class FakeProvider implements ActOnBehalfPort {
  readonly provider = "fake";
  supports(capability: string): boolean {
    return capability === "calendar";
  }
  async credentialFor(
    _ctx: ActContext,
    capability: string,
    _scopes: string[],
  ): Promise<UserCredential> {
    if (!this.supports(capability)) {
      throw new ActOnBehalfUnavailable(
        `the fake provider does not support '${capability}'.`,
      );
    }
    return { bearer: "fake-token", apiBase: "https://api.fake.test", expiresAt: 1 };
  }
}

describe("ActOnBehalfPort contract (TS parity)", () => {
  test("ActContext.rawToken is optional — the Microsoft↔Google asymmetry", () => {
    const google: ActContext = {
      providerHint: "google",
      tenant: "ws-1",
      subject: "u@example.test",
      claims: { hd: "example.test" },
    };
    expect(google.rawToken).toBeUndefined();

    const microsoft: ActContext = {
      providerHint: "microsoft",
      tenant: "ws-1",
      subject: "user-oid-1",
      rawToken: "eyJ.inbound.sig",
      claims: { tid: "tid-1" },
    };
    expect(microsoft.rawToken).toBe("eyJ.inbound.sig");
  });

  test("a fake provider satisfies the interface and round-trips", async () => {
    const prov = new FakeProvider();
    expect(prov.provider).toBe("fake");
    expect(prov.supports("calendar")).toBe(true);
    expect(prov.supports("mail")).toBe(false);
    const ctx: ActContext = {
      providerHint: "fake",
      tenant: "ws-1",
      subject: "s",
      claims: {},
    };
    const cred = await prov.credentialFor(ctx, "calendar", ["scope.read"]);
    expect(cred.bearer).toBe("fake-token");
    expect(cred.apiBase).toBe("https://api.fake.test");
  });

  test("unsupported capability throws ActOnBehalfUnavailable", async () => {
    const prov = new FakeProvider();
    const ctx: ActContext = {
      providerHint: "fake",
      tenant: "ws-1",
      subject: "s",
      claims: {},
    };
    await expect(prov.credentialFor(ctx, "mail", ["m.read"])).rejects.toBeInstanceOf(
      ActOnBehalfUnavailable,
    );
  });
});
