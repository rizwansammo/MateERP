"""Approval policies and decisions.

Domain apps register an executor per action code (``register_executor``);
approving a request runs the executor inside the same transaction, so the
decision and its effect succeed or fail together.
"""

from collections.abc import Callable

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpRequest
from django.utils import timezone
from rest_framework import exceptions

from apps.accounts.authorization import get_permission_codes, is_administrator
from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.audit.services import record
from apps.core.exceptions import BusinessRuleViolation

from .catalog import ACTIONS, BY_KEY, CATEGORIES
from .models import ApprovalPolicy, ApprovalRequest

# executor(request, approval_request, approver) -> result reference string
Executor = Callable[[HttpRequest, ApprovalRequest, User], str]
_executors: dict[str, Executor] = {}


def register_executor(action: str, executor: Executor) -> None:
    _executors[action] = executor


def ensure_policies() -> None:
    for category in CATEGORIES:
        ApprovalPolicy.objects.get_or_create(category=category.key)


def policy_for_action(action: str) -> ApprovalPolicy | None:
    category = ACTIONS.get(action)
    if category is None:
        return None
    return ApprovalPolicy.objects.select_related("approver_role").filter(category=category).first()


def approval_required(action: str) -> bool:
    policy = policy_for_action(action)
    return bool(policy and policy.in_force)


def _policy_snapshot(policy: ApprovalPolicy) -> dict:
    return {
        "is_required": policy.is_required,
        "is_active": policy.is_active,
        "approver_role": policy.approver_role.name if policy.approver_role else None,
        "amount_threshold": (
            str(policy.amount_threshold) if policy.amount_threshold is not None else None
        ),
        "allow_self_approval": policy.allow_self_approval,
        "notes": policy.notes,
    }


@transaction.atomic
def update_policy(request: HttpRequest, policy: ApprovalPolicy, data: dict) -> ApprovalPolicy:
    policy = ApprovalPolicy.objects.select_for_update().get(pk=policy.pk)
    category = BY_KEY[policy.category]
    if not category.supports_threshold and data.get("amount_threshold") is not None:
        raise exceptions.ValidationError(
            {"amount_threshold": ["This category does not use an amount threshold."]}
        )
    role = data.get("approver_role", policy.approver_role)
    if role is not None and not role.is_active:
        raise exceptions.ValidationError({"approver_role": ["This role is inactive."]})
    before = _policy_snapshot(policy)
    for field, value in data.items():
        setattr(policy, field, value)
    policy.updated_by = request.user
    policy.save()
    after = _policy_snapshot(policy)
    if before != after:
        record(
            "approval.policy_updated",
            request=request,
            target_type="approvals.approvalpolicy",
            target_id=policy.category,
            target_label=category.label,
            before=before,
            after=after,
        )
    return policy


def submit(
    request: HttpRequest, *, action: str, title: str, payload: dict, reason: str = ""
) -> ApprovalRequest:
    """Create a pending request for an action whose policy is in force."""
    category = ACTIONS[action]
    try:
        with transaction.atomic():
            approval = ApprovalRequest.objects.create(
                category=category,
                action=action,
                title=title,
                payload=payload,
                requested_by=request.user,
                request_reason=reason,
            )
            record(
                "approval.requested",
                request=request,
                target=approval,
                after={"action": action, "title": title},
                reason=reason,
            )
    except IntegrityError as exc:
        raise BusinessRuleViolation(
            "A request for this action is already waiting for approval.",
            code="approval_already_pending",
        ) from exc
    return approval


def can_decide(user: User, approval: ApprovalRequest) -> tuple[bool, str]:
    """Whether ``user`` may decide ``approval`` (and why not)."""
    if approval.status != ApprovalRequest.Status.PENDING:
        return False, "This request has already been decided."
    policy = (
        ApprovalPolicy.objects.select_related("approver_role")
        .filter(category=approval.category)
        .first()
    )
    if policy is None:
        return False, "No approval policy exists for this request."
    if approval.requested_by_id == user.pk and not policy.allow_self_approval:
        return False, "You cannot approve your own request."
    if is_administrator(user):
        return True, ""
    if policy.approver_role_id and user.role_id == policy.approver_role_id:
        return True, ""
    return False, "Your role is not the designated approver for this request."


def actionable_for(user: User):
    """Pending requests ``user`` may decide."""
    qs = ApprovalRequest.objects.filter(status=ApprovalRequest.Status.PENDING)
    eligible = []
    for approval in qs.select_related("requested_by"):
        allowed, _ = can_decide(user, approval)
        if allowed:
            eligible.append(approval.pk)
    return ApprovalRequest.objects.filter(pk__in=eligible)


def visible_to(user: User):
    """Requests the user may see: managers see all; others their own and decidable ones."""
    if "approvals.manage" in get_permission_codes(user):
        return ApprovalRequest.objects.all()
    decidable = actionable_for(user).values_list("pk", flat=True)
    return ApprovalRequest.objects.filter(Q(requested_by=user) | Q(pk__in=list(decidable)))


def decide(
    request: HttpRequest, approval_id: int, *, approve: bool, reason: str = ""
) -> ApprovalRequest:
    if not approve and not reason.strip():
        raise exceptions.ValidationError({"reason": ["Give a reason for rejecting."]})
    with transaction.atomic():
        approval = ApprovalRequest.objects.select_for_update().filter(pk=approval_id).first()
        if approval is None:
            raise exceptions.NotFound()
        allowed, why = can_decide(request.user, approval)
        if allowed:
            return _apply_decision(request, approval, approve=approve, reason=reason)
    # Recorded outside the rolled-back transaction so the denial is kept.
    record(
        "approval.decision_denied",
        request=request,
        target=approval,
        outcome=AuditEvent.Outcome.DENIED,
        reason=why,
    )
    raise exceptions.PermissionDenied(why)


def _apply_decision(
    request: HttpRequest, approval: ApprovalRequest, *, approve: bool, reason: str
) -> ApprovalRequest:
    user: User = request.user
    approval.reviewed_by = user
    approval.reviewed_at = timezone.now()
    approval.decision_reason = reason.strip()
    if approve:
        executor = _executors.get(approval.action)
        if executor is None:
            raise BusinessRuleViolation("This action cannot be executed.", code="no_executor")
        approval.result_reference = executor(request, approval, user)
        approval.status = ApprovalRequest.Status.APPROVED
    else:
        approval.status = ApprovalRequest.Status.REJECTED
    approval.save()
    record(
        "approval.approved" if approve else "approval.rejected",
        request=request,
        target=approval,
        after={"status": approval.status, "result": approval.result_reference or None},
        reason=approval.decision_reason,
    )
    return approval


@transaction.atomic
def cancel(request: HttpRequest, approval_id: int) -> ApprovalRequest:
    approval = ApprovalRequest.objects.select_for_update().filter(pk=approval_id).first()
    if approval is None:
        raise exceptions.NotFound()
    if approval.requested_by_id != request.user.pk:
        raise exceptions.PermissionDenied("Only the requester can withdraw a request.")
    if approval.status != ApprovalRequest.Status.PENDING:
        raise BusinessRuleViolation("This request has already been decided.", code="decided")
    approval.status = ApprovalRequest.Status.CANCELLED
    approval.reviewed_at = timezone.now()
    approval.save()
    record("approval.cancelled", request=request, target=approval)
    return approval
