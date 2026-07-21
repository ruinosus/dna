"""s-account-scoped-plan — ``dna.tenancy.accounts``: WHO the billing account is.

The subscription belongs to a billing ACCOUNT, so a workspace records which
account owns it at creation. This suite pins the one question that leaves open:
given a VERIFIED sign-in, which account is this?

No entity was invented. The auth layer already carries a per-IdP "which
org/tenant is this token from" claim, configured per provider block as
``tenant_claim`` and defaulted per type (entra→``tid``, workos/clerk/auth0→
``org_id``, google→``hd``) — the same string the portal's plan table and the
Stripe customer's ``metadata.tenant`` have always been keyed by.

**Every ambiguity resolves to ``None``**, and ``None`` means the Free floor. The
asymmetry is deliberate: a wrong ``None`` under-serves a customer until they
complain; a wrong non-``None`` makes one account pay for another's usage, or
leaks one account's paid tier to strangers.
"""
from __future__ import annotations

import pytest

from dna.tenancy import (
    DNA_TENANT_CLAIM_MARKER,
    MSA_SHARED_TENANT_ID,
    account_id_from_claims,
    is_account_id,
)


# ---------------------------------------------------------------------------
# 1. The per-provider account claim — what already exists, reused
# ---------------------------------------------------------------------------

def test_entra_tid_is_the_account():
    """Lane A (Microsoft Entra). ``tid`` is the Azure org — the same value the
    portal's plan table is keyed by and Stripe carries in ``metadata.tenant``."""
    assert account_id_from_claims(
        {"oid": "o1", "email": "a@acme.com",
         "tid": "c5b891f7-65c2-4417-a5af-22cab24dc1d5"}
    ) == "c5b891f7-65c2-4417-a5af-22cab24dc1d5"


def test_workos_org_id_is_the_account():
    assert account_id_from_claims(
        {"sub": "user_01H", "email": "a@acme.com", "org_id": "org_01HXYZ"}
    ) == "org_01HXYZ"


def test_google_workspace_hd_is_the_account():
    assert account_id_from_claims(
        {"sub": "1234", "email": "a@acme.com", "hd": "acme.com"}
    ) == "acme.com"


def test_the_stamped_provider_claim_wins_over_the_fallbacks():
    """A configured deployment stamps WHICH claim its provider block reads the
    account from (``_dna_tenant_claim``). That stamp must win: a token can carry
    several org-ish claims, and the provider's configuration is the authority on
    which one is the account here."""
    claims = {
        DNA_TENANT_CLAIM_MARKER: "org_id",
        "org_id": "org_configured",
        "tid": "tid-should-lose",
        "tenant": "tenant-should-lose",
    }
    assert account_id_from_claims(claims) == "org_configured"


def test_an_explicit_claim_key_wins_over_everything():
    claims = {DNA_TENANT_CLAIM_MARKER: "org_id", "org_id": "org_x",
              "custom_account": "acct-explicit"}
    assert account_id_from_claims(claims, claim_key="custom_account") == "acct-explicit"


def test_the_generic_tenant_claim_is_honoured():
    assert account_id_from_claims({"tenant": "acme"}) == "acme"


def test_fallback_order_is_tid_then_org_id_then_hd():
    assert account_id_from_claims({"tid": "T", "org_id": "O", "hd": "H"}) == "T"
    assert account_id_from_claims({"org_id": "O", "hd": "H"}) == "O"
    assert account_id_from_claims({"hd": "H"}) == "H"


def test_a_claim_delivered_as_a_list_still_resolves():
    assert account_id_from_claims({"tid": ["T1"]}) == "T1"


# ---------------------------------------------------------------------------
# 2. FAIL-CLOSED — no account is a legitimate, expected answer
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("claims", [
    None,
    {},
    {"oid": "o1", "email": "someone@gmail.com"},   # consumer lane, no org.
    {"tid": ""},
    {"tid": "   "},
    {"org_id": None},
])
def test_no_resolvable_account_is_none_never_a_guess(claims):
    """A sign-in with no account claim has NO account. It is never defaulted to
    the identity, the email domain, or anything else — every one of those would
    be an invented billing entity, and any two users landing on the same invented
    value would share a subscription neither bought."""
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


@pytest.mark.parametrize("value", ["common", "organizations", "consumers",
                                   "none", "null", "undefined", "-"])
def test_authority_placeholders_are_never_accounts(value):
    """``common``/``organizations``/``consumers`` are Entra AUTHORITY
    placeholders, not tenants — they arrive when something upstream copied the
    authority URL segment into the claim. Treating one as an account would merge
    every deployment that made the same mistake into a single payer."""
    assert account_id_from_claims({"tid": value}) is None


def test_a_rejected_value_does_not_block_a_later_valid_claim():
    """A useless ``tid`` must not shadow a real ``org_id`` — the resolver keeps
    probing rather than giving up on the first present-but-unusable claim."""
    assert account_id_from_claims(
        {"tid": MSA_SHARED_TENANT_ID, "org_id": "org_real"}
    ) == "org_real"


# ---------------------------------------------------------------------------
# 3. Isolation — two identities are the same account IFF the claim matches
# ---------------------------------------------------------------------------

def test_two_identities_in_one_org_share_the_account():
    """Colleagues share a subscription — that is the product decision working:
    the account buys once for everyone in it."""
    a = account_id_from_claims({"oid": "o1", "email": "a@acme.com", "tid": "T"})
    b = account_id_from_claims({"oid": "o2", "email": "b@acme.com", "tid": "T"})
    assert a == b == "T"


def test_two_identities_in_different_orgs_are_different_accounts():
    a = account_id_from_claims({"oid": "o1", "email": "a@acme.com", "tid": "T1"})
    b = account_id_from_claims({"oid": "o2", "email": "b@globex.com", "tid": "T2"})
    assert a != b


def test_same_email_different_org_is_a_different_account():
    """The account is the ORG claim, never the email or its domain. An email is
    reassignable and a domain is not IdP-vouched; the org claim is."""
    assert account_id_from_claims({"email": "a@acme.com", "tid": "T1"}) != \
        account_id_from_claims({"email": "a@acme.com", "tid": "T2"})
