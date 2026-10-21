"""Domain posting authority: the narrow boundary between owning workflows and the ledger.

Owning apps (billing, purchasing) register their source types and the domain
permissions each source action requires. Their services call ``authorize()``
for the acting user and pass the returned ``PostingAuthority`` to
``post_journal``/``reverse``. No request field, flag or serializer can create
one: it exists only as a server-side object bound to one actor, source type
and action. Billing staff therefore never need ``accounting.manage``, and the
public journal API keeps requiring it.
"""

from rest_framework.exceptions import PermissionDenied

from apps.accounts.authorization import require

# Phase 3 sources owned by accounting and banking; never claimable by a domain app.
RESERVED_SOURCES = frozenset(
    {"manual", "opening", "adjustment", "reversal", "transfer", "bank_adjustment"}
)
# Accounts that only domain adapters may post to, so subledgers reconcile exactly.
SUBLEDGER_CONTROLS = frozenset(
    {
        "receivable",
        "payable",
        "customer_credit",
        "founder_payable",
        "founder_loan",
        "founder_pending",
        "founder_equity",
        "share_capital",
        "share_premium",
        "inventory",
        "grni",
        "unbilled_revenue",
        "deferred_revenue",
        "fixed_assets",
        "accumulated_depreciation",
        "asset_acquisition",
    }
)

_registry: dict[str, dict[str, tuple[str, ...]]] = {}
_TOKEN = object()


def register_source(source_type: str, actions: dict[str, tuple[str, ...]]) -> None:
    """Called from an owning app's ``ready()``; ``actions`` maps action → permission codes."""
    if source_type in RESERVED_SOURCES or not 1 <= len(source_type) <= 24:
        raise ValueError(f"Cannot register posting source {source_type!r}.")
    if not actions or any(not codes for codes in actions.values()):
        raise ValueError("Every registered source action needs domain permissions.")
    _registry[source_type] = {action: tuple(codes) for action, codes in actions.items()}


def is_domain_source(source_type: str) -> bool:
    return source_type in _registry


class PostingAuthority:
    """Proof that ``actor`` may perform one registered source action now."""

    __slots__ = ("actor", "source_action", "source_type")

    def __init__(self, token, actor, source_type: str, source_action: str):
        if token is not _TOKEN:
            raise TypeError("A posting authority is issued only by authorize().")
        self.actor = actor
        self.source_type = source_type
        self.source_action = source_action

    def __setattr__(self, name, value):
        if hasattr(self, name):
            raise AttributeError("A posting authority is immutable.")
        object.__setattr__(self, name, value)

    def verify(self, actor, source_type: str | None = None, source_action: str | None = None):
        if (
            actor is None
            or self.actor.pk != actor.pk
            or (source_type is not None and source_type != self.source_type)
            or (source_action is not None and source_action != self.source_action)
        ):
            raise PermissionDenied("The posting authority does not cover this operation.")


def authorize(actor, source_type: str, source_action: str) -> PostingAuthority:
    """Check the domain permissions registered for this action and issue an authority."""
    codes = _registry.get(source_type, {}).get(source_action)
    if codes is None:
        raise PermissionDenied("This posting source is not registered.")
    if actor is None or not actor.is_active or actor.must_change_password:
        raise PermissionDenied()
    require(actor, *codes)
    return PostingAuthority(_TOKEN, actor, source_type, source_action)
