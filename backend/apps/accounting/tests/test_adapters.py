"""The domain posting boundary: authority without accounting.manage, never a public bypass."""

from datetime import date
from types import SimpleNamespace

import pytest
from rest_framework.exceptions import APIException, PermissionDenied

from apps.accounting.models import JournalEntry
from apps.accounting.services import adapters, posting, setup
from apps.approvals.models import ApprovalPolicy

pytestmark = pytest.mark.django_db
DAY = date(2026, 10, 10)
SOURCE = "adapter_probe"


@pytest.fixture(autouse=True)
def probe_source():
    adapters.register_source(SOURCE, {"post": ("invoices.issue",), "void": ("invoices.issue",)})
    yield
    adapters._registry.pop(SOURCE, None)


@pytest.fixture
def receivable(finance):
    request, accounts = finance
    return setup.save_account(request, {"control": "receivable"}, accounts["1100"].pk)


def lines(accounts, receivable):
    return [
        {"account_id": receivable.pk, "debit": "11000"},
        {"account_id": accounts["4100"].pk, "credit": "10000"},
        {"account_id": accounts["2100"].pk, "credit": "1000"},
    ]


def domain_post(user, accounts, receivable, *, authority=None, source_id="inv-1"):
    return posting.post_journal(
        actor=user,
        posting_key=f"probe-{source_id}-key",
        source_type=SOURCE,
        source_id=source_id,
        source_action="post",
        posting_date=DAY,
        description="Invoice issued",
        lines=lines(accounts, receivable),
        authority=authority or adapters.authorize(user, SOURCE, "post"),
    )


def test_billing_user_posts_without_accounting_manage(finance, receivable, user_with):
    _, accounts = finance
    clerk = user_with("clerk", "invoices.issue")
    policy = ApprovalPolicy.objects.get(category="financial_adjustments")
    policy.is_required = True
    policy.save()
    journal = domain_post(clerk, accounts, receivable)
    # The domain applies its own approval; the generic manual-journal policy does not hold it.
    assert journal.status == "posted" and journal.posted_by == clerk
    assert journal.source_type == SOURCE
    # Same source identity retried returns the same journal.
    assert domain_post(clerk, accounts, receivable).pk == journal.pk
    # The clerk still cannot use any public accounting path.
    with pytest.raises(PermissionDenied):
        posting.save_draft(SimpleNamespace(user=clerk, META={}), {"lines": []})


def test_authority_requires_registration_permission_and_binding(finance, receivable, user_with):
    _, accounts = finance
    clerk = user_with("clerk", "invoices.issue")
    other = user_with("other", "invoices.issue")
    viewer = user_with("viewer2", "finance.view")
    with pytest.raises(PermissionDenied):
        adapters.authorize(viewer, SOURCE, "post")
    with pytest.raises(PermissionDenied):
        adapters.authorize(clerk, "manual", "post")
    with pytest.raises(PermissionDenied):
        adapters.authorize(clerk, SOURCE, "unregistered_action")
    with pytest.raises(TypeError):
        adapters.PostingAuthority(object(), clerk, SOURCE, "post")
    authority = adapters.authorize(clerk, SOURCE, "post")
    with pytest.raises(AttributeError):
        authority.actor = other
    with pytest.raises(PermissionDenied):
        domain_post(other, accounts, receivable, authority=authority)
    void = adapters.authorize(clerk, SOURCE, "void")
    with pytest.raises(PermissionDenied):
        domain_post(clerk, accounts, receivable, authority=void)
    with pytest.raises(ValueError):
        adapters.register_source("manual", {"post": ("invoices.issue",)})
    assert not JournalEntry.objects.filter(source_type=SOURCE).exists()


def test_inactive_or_password_pending_actor_is_refused(user_with):
    clerk = user_with("clerk", "invoices.issue")
    clerk.must_change_password = True
    with pytest.raises(PermissionDenied):
        adapters.authorize(clerk, SOURCE, "post")


def test_domain_source_never_posts_without_authority(finance, receivable):
    request, accounts = finance
    with pytest.raises(PermissionDenied):
        posting.post_journal(
            actor=request.user,
            posting_key="no-authority-key",
            source_type=SOURCE,
            source_id="x",
            source_action="post",
            posting_date=DAY,
            description="Bypass attempt",
            lines=lines(accounts, receivable),
        )


def test_subledger_controls_reject_manual_and_treasury_postings(finance, receivable):
    request, accounts = finance
    with pytest.raises(APIException) as manual:
        posting.save_draft(
            request,
            {
                "posting_date": DAY,
                "description": "Manual receivable",
                "lines": [
                    {"account_id": receivable.pk, "debit": "10"},
                    {"account_id": accounts["4100"].pk, "credit": "10"},
                ],
            },
        )
    assert manual.value.get_codes() == "subledger_control"
    with pytest.raises(APIException):
        posting.post_journal(
            actor=request.user,
            posting_key="treasury-like-key",
            source_type="bank_adjustment",
            source_id="t1",
            source_action="post",
            posting_date=DAY,
            description="Bank adjustment",
            lines=[
                {"account_id": accounts["1020"].pk, "debit": "10"},
                {"account_id": receivable.pk, "credit": "10"},
            ],
        )


def test_draft_saved_before_control_assignment_cannot_post(finance):
    request, accounts = finance
    draft = posting.save_draft(
        request,
        {
            "posting_date": DAY,
            "description": "Pre-mapping draft",
            "lines": [
                {"account_id": accounts["1100"].pk, "debit": "10"},
                {"account_id": accounts["4100"].pk, "credit": "10"},
            ],
        },
    )
    setup.save_account(request, {"control": "receivable"}, accounts["1100"].pk)
    with pytest.raises(APIException) as blocked:
        posting.post_draft(request, draft.pk, "pre-mapping-draft-key")
    assert blocked.value.get_codes() == "subledger_control"


def test_domain_journals_reverse_only_through_owning_workflow(finance, receivable, user_with):
    request, accounts = finance
    clerk = user_with("clerk", "invoices.issue")
    journal = domain_post(clerk, accounts, receivable)
    with pytest.raises(APIException) as public:
        posting.reverse(request, journal.pk, DAY, "Wrong customer", "public-reverse-key")
    assert public.value.get_codes() == "domain_owned"
    clerk_request = SimpleNamespace(user=clerk, META={})
    reversal = posting.reverse(
        clerk_request,
        journal.pk,
        DAY,
        "Void invoice",
        "domain-reverse-key",
        authority=adapters.authorize(clerk, SOURCE, "void"),
    )
    assert reversal.status == "posted" and reversal.reversal_of_id == journal.pk


def test_subledger_control_requires_multicurrency_postable(finance):
    request, accounts = finance
    with pytest.raises(APIException):
        setup.save_account(request, {"control": "payable", "currency": "USD"}, accounts["2010"].pk)
    with pytest.raises(APIException):
        setup.save_account(request, {"control": "receivable"}, accounts["1000"].pk)
