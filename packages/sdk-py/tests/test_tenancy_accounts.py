"""s-account-scoped-plan — ``dna.tenancy.accounts``: WHO the billing account is.

The subscription belongs to a billing ACCOUNT, so a workspace records which
account owns it at creation. This suite pins the one question that leaves open:
given a VERIFIED sign-in, which account is this?

No entity was invented. The auth layer already carries a per-IdP "which
org/tenant is this token from" claim, configured per provider block as
``tenant_claim`` and defaulted per type (entra→``tid``, workos/clerk/auth0→
``org_id``, google→``hd``) — the same string the portal's plan table and the
Stripe customer's ``metadata.tenant`` have always been keyed by.

TWO THINGS THIS SUITE NOW ALSO PINS
-----------------------------------

1. **The consumer lane can be sold to.** A sign-in that belongs to no
   organization used to resolve to no account — permanent Free, no way to buy —
   which blocked monetizing the product's own wedge (an individual story). Now
   the PERSON is the account: the durable ``sub`` of the identity.

2. **The id says what kind of account it is.** Every ``account_id`` is
   namespaced by provider AND kind (``entra-org:``, ``workos-org:``,
   ``workos-user:``, …). That kills the theoretical collision between a ``tid``
   and a ``sub`` that share a literal value, and makes an id legible in a Stripe
   record or a support ticket — which will matter the day a person and a company
   are priced differently. The prefix is NEVER parsed for authorization.

**Every ambiguity resolves to ``None``**, and ``None`` means the Free floor. The
asymmetry is deliberate: a wrong ``None`` under-serves a customer until they
complain; a wrong non-``None`` makes one account pay for another's usage, or
leaks one account's paid tier to strangers.
"""
from __future__ import annotations

import pytest

from dna.tenancy import (
    DNA_PROVIDER_FAMILY_MARKER,
    DNA_PROVIDER_TYPE_MARKER,
    DNA_TENANT_CLAIM_MARKER,
    MSA_SHARED_TENANT_ID,
    PROVIDER_ACCOUNT_NAMESPACES,
    account_id_from_claims,
    is_account_id,
    provider_type_from_claims,
)


# ---------------------------------------------------------------------------
# 1. The per-provider account claim — what already exists, reused + namespaced
# ---------------------------------------------------------------------------

def test_entra_tid_is_the_account():
    """Lane A (Microsoft Entra). ``tid`` is the Azure org — the same value the
    portal's plan table is keyed by and Stripe carries in ``metadata.tenant``,
    now carried in the Entra ORG namespace."""
    assert account_id_from_claims(
        {"oid": "o1", "email": "a@acme.com",
         "tid": "c5b891f7-65c2-4417-a5af-22cab24dc1d5"}
    ) == "entra-org:c5b891f7-65c2-4417-a5af-22cab24dc1d5"


def test_workos_org_id_is_the_account():
    assert account_id_from_claims(
        {DNA_PROVIDER_TYPE_MARKER: "workos",
         "sub": "user_01H", "email": "a@acme.com", "org_id": "org_01HXYZ"}
    ) == "workos-org:org_01HXYZ"


def test_google_workspace_hd_is_the_account():
    assert account_id_from_claims(
        {"sub": "1234", "email": "a@acme.com", "hd": "acme.com"}
    ) == "google-org:acme.com"


def test_clerk_and_auth0_orgs_get_their_own_namespaces():
    """Every provider the module knows follows the same shape — the pattern is
    not special-cased for the two lanes that ship today."""
    assert account_id_from_claims(
        {DNA_PROVIDER_TYPE_MARKER: "clerk", "org_id": "org_2a"}
    ) == "clerk-org:org_2a"
    assert account_id_from_claims(
        {DNA_PROVIDER_TYPE_MARKER: "auth0", "org_id": "org_b7"}
    ) == "auth0-org:org_b7"


def test_the_stamped_provider_claim_wins_over_the_fallbacks():
    """A configured deployment stamps WHICH claim its provider block reads the
    account from (``_dna_tenant_claim``). That stamp must win: a token can carry
    several org-ish claims, and the provider's configuration is the authority on
    which one is the account here."""
    claims = {
        DNA_PROVIDER_TYPE_MARKER: "workos",
        DNA_TENANT_CLAIM_MARKER: "org_id",
        "org_id": "org_configured",
        "tid": "tid-should-lose",
        "tenant": "tenant-should-lose",
    }
    assert account_id_from_claims(claims) == "workos-org:org_configured"


def test_an_explicit_claim_key_wins_over_everything():
    claims = {DNA_TENANT_CLAIM_MARKER: "org_id", "org_id": "org_x",
              "custom_account": "acct-explicit"}
    assert account_id_from_claims(claims, claim_key="custom_account") == \
        "tenant:acct-explicit"


def test_the_generic_tenant_claim_is_honoured():
    assert account_id_from_claims({"tenant": "acme"}) == "tenant:acme"


def test_fallback_order_is_tid_then_org_id_then_hd():
    assert account_id_from_claims({"tid": "T", "org_id": "O", "hd": "H"}) == "entra-org:T"
    assert account_id_from_claims({"org_id": "O", "hd": "H"}) == "tenant:O"
    assert account_id_from_claims({"hd": "H"}) == "google-org:H"


def test_an_unnamed_provider_falls_to_the_generic_namespace_not_a_guess():
    """``org_id`` is the default account claim of THREE providers (workos, clerk,
    auth0), so on its own it names none of them. Guessing one would stamp an id
    that a later, correctly-stamped sign-in of the SAME account would not match —
    the account would silently split in two. The honest ``tenant:`` namespace
    keeps it unique and keeps it one account."""
    assert account_id_from_claims({"org_id": "org_01HXYZ"}) == "tenant:org_01HXYZ"


def test_a_claim_delivered_as_a_list_still_resolves():
    assert account_id_from_claims({"tid": ["T1"]}) == "entra-org:T1"


def test_the_idp_value_is_never_re_encoded():
    """The account id must carry the provider's own string byte-for-byte — it is
    what a human pastes into Stripe or a support ticket, and what the plan doc is
    keyed by. Only the prefix is ours."""
    assert account_id_from_claims({DNA_PROVIDER_TYPE_MARKER: "auth0",
                                   "org_id": "Org_MiXeD|Case"}) == \
        "auth0-org:Org_MiXeD|Case"


# ---------------------------------------------------------------------------
# 2. THE CONSUMER LANE — a person with no organization is a sellable account
# ---------------------------------------------------------------------------

def test_a_workos_person_with_no_org_is_their_own_account():
    """THE HOLE THIS CLOSES. dna-cloud's Lane B (WorkOS AuthKit, consumer/Google)
    issues tokens with NO ``org_id`` — an individual, which is exactly the
    product's wedge. That used to resolve to no account at all: permanent Free
    with no way to buy. The person IS the account now, keyed on the durable
    WorkOS user id."""
    assert account_id_from_claims(
        {DNA_PROVIDER_TYPE_MARKER: "workos",
         "sub": "user_01HXYZABC", "email": "someone@gmail.com"}
    ) == "workos-user:user_01HXYZABC"


def test_the_real_lane_b_token_shape_resolves_via_the_family_stamp_alone():
    """``workos_provider_from_env`` — the ACTUAL Lane-B verifier dna-cloud runs —
    stamps ONLY the provider FAMILY; it writes no tenant-claim and no type stamp.
    If the resolver needed the type stamp, the real consumer lane would still
    resolve to nothing and this whole change would be theatre. The family is
    mapped back to the type."""
    claims = {DNA_PROVIDER_FAMILY_MARKER: "workos",
              "sub": "user_01HREAL", "email": "someone@gmail.com"}
    assert provider_type_from_claims(claims) == "workos"
    assert account_id_from_claims(claims) == "workos-user:user_01HREAL"


def test_the_organization_always_beats_the_person():
    """A WorkOS user who belongs to an org bills to the ORG, never to themselves
    — otherwise an employee of a paying customer would be handed their own
    (unpaid) account and drop to Free while their colleagues are Pro."""
    assert account_id_from_claims(
        {DNA_PROVIDER_TYPE_MARKER: "workos",
         "sub": "user_01H", "org_id": "org_01HXYZ"}
    ) == "workos-org:org_01HXYZ"


def test_two_people_on_the_consumer_lane_are_two_accounts():
    """The point of the lane: each person pays for themselves. If these ever
    collapsed to one id, the first subscriber would upgrade the other and both
    would meter against one bill."""
    a = account_id_from_claims({DNA_PROVIDER_TYPE_MARKER: "workos", "sub": "user_a"})
    b = account_id_from_claims({DNA_PROVIDER_TYPE_MARKER: "workos", "sub": "user_b"})
    assert a != b
    assert a == "workos-user:user_a"


def test_the_same_person_resolves_to_the_same_account_every_sign_in():
    """The account must be DURABLE — it is what a Stripe subscription is keyed
    by. Nothing volatile (email, name, session) may enter it."""
    first = account_id_from_claims(
        {DNA_PROVIDER_TYPE_MARKER: "workos", "sub": "user_01H",
         "email": "old@gmail.com", "name": "Old Name"}
    )
    later = account_id_from_claims(
        {DNA_PROVIDER_TYPE_MARKER: "workos", "sub": "user_01H",
         "email": "new@proton.me", "name": "New Name"}
    )
    assert first == later == "workos-user:user_01H"


@pytest.mark.parametrize("ptype,expected", [
    ("workos", "workos-user:S"),
    ("clerk", "clerk-user:S"),
    ("auth0", "auth0-user:S"),
    ("google", "google-user:S"),
])
def test_every_provider_with_a_durable_subject_has_a_person_lane(ptype, expected):
    assert account_id_from_claims({DNA_PROVIDER_TYPE_MARKER: ptype, "sub": "S"}) \
        == expected


def test_entra_has_no_person_lane_so_a_personal_msa_still_has_no_account():
    """Entra is deliberately EXCLUDED from the consumer lane. Its ``sub`` is
    PAIRWISE — unique per (user, application) — so the same human presents a
    different ``sub`` to a different app registration, and two DNA faces would
    bill one person twice. Its durable id is ``oid``, but making a personal
    Microsoft account billable is a product decision that has not been taken.
    Until it is, this sign-in fails closed to Free rather than to an invented
    identifier."""
    assert PROVIDER_ACCOUNT_NAMESPACES["entra"].person is None
    assert account_id_from_claims(
        {DNA_PROVIDER_TYPE_MARKER: "entra", "tid": MSA_SHARED_TENANT_ID,
         "sub": "pairwise-sub", "oid": "o1", "email": "someone@outlook.com"}
    ) is None


def test_an_unnamed_provider_gets_no_person_lane():
    """A ``sub`` from an IdP we cannot name proves nothing about durability or
    uniqueness — a generic OIDC provider may well issue a pairwise or recycled
    subject. Fail closed."""
    assert account_id_from_claims({"sub": "whoever", "email": "a@b.com"}) is None
    assert account_id_from_claims(
        {DNA_PROVIDER_TYPE_MARKER: "oidc", "sub": "whoever"}
    ) is None


# ---------------------------------------------------------------------------
# 3. THE NAMESPACE'S REASON TO EXIST — a tid and a sub cannot collide
# ---------------------------------------------------------------------------

def test_a_tid_and_a_sub_of_the_same_literal_value_are_different_accounts():
    """THE collision the namespace prevents. Both claims are opaque strings from
    unrelated issuers; nothing stops them from being byte-identical. Un-namespaced
    they were the SAME ``account_id`` — one AccountPlan, one Stripe customer, an
    Entra organization and a stranger on the consumer lane sharing a subscription
    and a quota. The prefix makes that structurally impossible."""
    same = "c5b891f7-65c2-4417-a5af-22cab24dc1d5"
    org = account_id_from_claims({"tid": same})
    person = account_id_from_claims({DNA_PROVIDER_TYPE_MARKER: "workos", "sub": same})
    assert org == "entra-org:" + same
    assert person == "workos-user:" + same
    assert org != person


def test_an_org_and_a_person_of_the_same_provider_cannot_collide_either():
    """Same issuer, same literal — a WorkOS ``org_id`` and a WorkOS ``sub``. The
    kind is part of the id, so the company and the individual stay two accounts."""
    same = "id_01HXYZ"
    org = account_id_from_claims({DNA_PROVIDER_TYPE_MARKER: "workos", "org_id": same})
    person = account_id_from_claims({DNA_PROVIDER_TYPE_MARKER: "workos", "sub": same})
    assert org == "workos-org:id_01HXYZ"
    assert person == "workos-user:id_01HXYZ"
    assert org != person


def test_the_same_literal_org_id_from_two_providers_are_two_accounts():
    same = "org_01HXYZ"
    a = account_id_from_claims({DNA_PROVIDER_TYPE_MARKER: "workos", "org_id": same})
    b = account_id_from_claims({DNA_PROVIDER_TYPE_MARKER: "clerk", "org_id": same})
    assert a != b


def test_every_namespace_is_distinct():
    """A duplicated prefix would silently re-open the collision this whole
    mechanism exists to close — assert on the table itself so a careless edit
    fails here rather than in production billing."""
    prefixes = []
    for ns in PROVIDER_ACCOUNT_NAMESPACES.values():
        prefixes.append(ns.org)
        if ns.person:
            prefixes.append(ns.person)
    assert len(prefixes) == len(set(prefixes))


# ---------------------------------------------------------------------------
# 4. FAIL-CLOSED — no account is a legitimate, expected answer
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("claims", [
    None,
    {},
    {"oid": "o1", "email": "someone@gmail.com"},   # no org, no named provider.
    {"tid": ""},
    {"tid": "   "},
    {"org_id": None},
    {DNA_PROVIDER_TYPE_MARKER: "workos", "email": "someone@gmail.com"},  # no sub.
    {DNA_PROVIDER_TYPE_MARKER: "workos", "sub": "  "},
])
def test_no_resolvable_account_is_none_never_a_guess(claims):
    """A sign-in with neither an organization nor a durable subject has NO
    account. It is never defaulted to the identity, the email domain, or anything
    else — every one of those would be an invented billing entity, and any two
    users landing on the same invented value would share a subscription neither
    bought."""
    assert account_id_from_claims(claims) is None


def test_the_shared_msa_tenant_is_never_an_account():
    """The sharp edge. EVERY personal Microsoft account (outlook/hotmail/live)
    presents Microsoft's well-known consumer tenant as its ``tid``. It identifies
    the consumer LANE, not a customer.

    Accepting it would put every personal-MSA user on the planet into ONE billing
    account: the first to subscribe would silently upgrade all of them, and all
    of their usage would meter against that one payer's quota and bill. It is
    refused — such a sign-in has no account and gets the Free floor."""
    # ⚠️ O LITERAL, de propósito. As asserções abaixo usam a constante, então
    # elas passam mesmo que o GUID esteja errado — testam o mecanismo ("recuse o
    # que estiver na lista"), não o FATO de que este é o tenant compartilhado do
    # MSA. Um dígito trocado aceitaria o tenant real e colocaria todo usuário
    # Microsoft pessoal numa única conta de cobrança. Este valor vem da
    # documentação da Microsoft e não muda.
    assert MSA_SHARED_TENANT_ID == "9188040d-6c67-4c5b-b112-36a304b66dad"
    assert account_id_from_claims({"tid": "9188040d-6c67-4c5b-b112-36a304b66dad"}) is None

    assert account_id_from_claims({"tid": MSA_SHARED_TENANT_ID}) is None
    assert is_account_id(MSA_SHARED_TENANT_ID) is False


def test_the_msa_refusal_survives_the_namespace():
    """The namespace must not have turned the refusal into
    ``entra-org:9188040d-…``, which would be the same catastrophe wearing a
    prefix — one account for every personal Microsoft user, just legibly so."""
    for claims in (
        {"tid": MSA_SHARED_TENANT_ID},
        {DNA_PROVIDER_TYPE_MARKER: "entra", "tid": MSA_SHARED_TENANT_ID},
        {DNA_PROVIDER_FAMILY_MARKER: "microsoft", "tid": MSA_SHARED_TENANT_ID},
        {DNA_TENANT_CLAIM_MARKER: "tid", "tid": MSA_SHARED_TENANT_ID},
        {"tenant": MSA_SHARED_TENANT_ID},
    ):
        assert account_id_from_claims(claims) is None


@pytest.mark.parametrize("value", ["common", "organizations", "consumers",
                                   "none", "null", "undefined", "-"])
def test_authority_placeholders_are_never_accounts(value):
    """``common``/``organizations``/``consumers`` are Entra AUTHORITY
    placeholders, not tenants — they arrive when something upstream copied the
    authority URL segment into the claim. Treating one as an account would merge
    every deployment that made the same mistake into a single payer."""
    assert account_id_from_claims({"tid": value}) is None


@pytest.mark.parametrize("value", ["common", "organizations", "consumers",
                                   "none", "null", "undefined", "-"])
def test_the_person_lane_refuses_the_same_placeholder_values(value):
    """The consumer lane is not a bypass around the refusal list — a ``sub`` is
    screened exactly like an org claim."""
    assert account_id_from_claims(
        {DNA_PROVIDER_TYPE_MARKER: "workos", "sub": value}
    ) is None


def test_a_rejected_value_does_not_block_a_later_valid_claim():
    """A useless ``tid`` must not shadow a real ``org_id`` — the resolver keeps
    probing rather than giving up on the first present-but-unusable claim."""
    assert account_id_from_claims(
        {DNA_PROVIDER_TYPE_MARKER: "workos",
         "tid": MSA_SHARED_TENANT_ID, "org_id": "org_real"}
    ) == "workos-org:org_real"


def test_a_rejected_org_claim_falls_through_to_the_person_lane():
    """A personal-MSA-style dead end on the org claim must not kill a provider
    that DOES have a consumer lane — the person is still an account."""
    assert account_id_from_claims(
        {DNA_PROVIDER_TYPE_MARKER: "workos", "org_id": "none", "sub": "user_01H"}
    ) == "workos-user:user_01H"


# ---------------------------------------------------------------------------
# 5. Isolation — two identities are the same account IFF the claim matches
# ---------------------------------------------------------------------------

def test_two_identities_in_one_org_share_the_account():
    """Colleagues share a subscription — that is the product decision working:
    the account buys once for everyone in it."""
    a = account_id_from_claims({"oid": "o1", "email": "a@acme.com", "tid": "T"})
    b = account_id_from_claims({"oid": "o2", "email": "b@acme.com", "tid": "T"})
    assert a == b == "entra-org:T"


def test_two_identities_in_different_orgs_are_different_accounts():
    a = account_id_from_claims({"oid": "o1", "email": "a@acme.com", "tid": "T1"})
    b = account_id_from_claims({"oid": "o2", "email": "b@globex.com", "tid": "T2"})
    assert a != b


def test_same_email_different_org_is_a_different_account():
    """The account is the ORG claim, never the email or its domain. An email is
    reassignable and a domain is not IdP-vouched; the org claim is."""
    assert account_id_from_claims({"email": "a@acme.com", "tid": "T1"}) != \
        account_id_from_claims({"email": "a@acme.com", "tid": "T2"})
