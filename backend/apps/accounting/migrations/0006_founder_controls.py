"""Extend protected account purposes without reinterpreting existing accounts."""

from importlib import import_module

from django.db import migrations

PREVIOUS = import_module("apps.accounting.migrations.0004_subledger_controls").GUARD
NEW = (
    PREVIOUS.replace(
        "('payable','customer_credit')",
        "('payable','customer_credit','founder_payable','founder_loan','founder_pending')",
    )
    .replace(
        "('receivable','payable','customer_credit')",
        "('receivable','payable','customer_credit','founder_payable','founder_loan','founder_pending','founder_equity','share_capital','share_premium')",
    )
    .replace(
        "NEW.control NOT IN",
        "(NEW.control IN ('founder_equity','share_capital','share_premium') AND NEW.account_type<>'equity') OR NEW.control NOT IN",
    )
    .replace(
        "'retained_earnings','receivable','payable','customer_credit'",
        "'retained_earnings','receivable','payable','customer_credit','founder_payable','founder_loan','founder_pending','founder_equity','share_capital','share_premium'",
    )
)


class Migration(migrations.Migration):
    dependencies = [("accounting", "0005_settlement_valuations")]
    operations = [migrations.RunSQL(NEW, PREVIOUS)]
