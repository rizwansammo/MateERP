from django.db import models
from django.db.models import Q

from apps.accounting.models import amount


class BankAccount(models.Model):
    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=8, choices=[("bank", "Bank"), ("cash", "Cash")])
    institution = models.CharField(max_length=160, blank=True)
    identifier = models.CharField(max_length=120, blank=True)
    currency = models.CharField(max_length=3)
    gl_account = models.OneToOneField(
        "accounting.Account", on_delete=models.PROTECT, related_name="bank_account"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "pk"]

    def __str__(self):
        return self.name


class TreasuryOperation(models.Model):
    reference = models.CharField(max_length=160, unique=True)
    journal = models.OneToOneField("accounting.JournalEntry", on_delete=models.PROTECT)
    kind = models.CharField(max_length=24)
    fingerprint = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.reference


class BankStatement(models.Model):
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT)
    reference = models.CharField(max_length=120)
    start = models.DateField()
    end = models.DateField()
    opening_balance = amount()
    closing_balance = amount()

    class Meta:
        ordering = ["-end", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["bank_account", "reference"], name="bank_statement_reference"
            ),
            models.CheckConstraint(
                condition=Q(end__gte=models.F("start")), name="statement_dates_valid"
            ),
        ]

    def __str__(self):
        return self.reference


class StatementLine(models.Model):
    statement = models.ForeignKey(BankStatement, on_delete=models.PROTECT, related_name="lines")
    position = models.PositiveIntegerField()
    date = models.DateField()
    description = models.CharField(max_length=300)
    reference = models.CharField(max_length=120, blank=True)
    amount = amount()

    class Meta:
        ordering = ["date", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["statement", "position"], name="statement_line_position"
            )
        ]

    def __str__(self):
        return f"{self.statement_id}:{self.position}"


class Reconciliation(models.Model):
    statement = models.OneToOneField(
        BankStatement, on_delete=models.PROTECT, related_name="reconciliation"
    )
    is_complete = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True)
    completed_by = models.ForeignKey("accounts.User", null=True, on_delete=models.PROTECT)
    evidence = models.JSONField(default=list)

    def __str__(self):
        return str(self.statement_id)


class MatchGroup(models.Model):
    reconciliation = models.ForeignKey(
        Reconciliation, on_delete=models.PROTECT, related_name="matches"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT)

    def __str__(self):
        return str(self.pk)


class StatementMatch(models.Model):
    group = models.ForeignKey(
        MatchGroup, on_delete=models.PROTECT, related_name="statement_members"
    )
    line = models.ForeignKey(StatementLine, on_delete=models.PROTECT, related_name="matches")
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["line"], condition=Q(is_active=True), name="statement_matched_once"
            )
        ]

    def __str__(self):
        return f"{self.group_id}:{self.line_id}"


class LedgerMatch(models.Model):
    group = models.ForeignKey(MatchGroup, on_delete=models.PROTECT, related_name="ledger_members")
    line = models.ForeignKey(
        "accounting.JournalLine", on_delete=models.PROTECT, related_name="matches"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["line"], condition=Q(is_active=True), name="ledger_matched_once"
            )
        ]

    def __str__(self):
        return f"{self.group_id}:{self.line_id}"
