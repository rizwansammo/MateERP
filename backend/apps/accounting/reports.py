"""Posted-ledger selectors. All report figures are calculated with Decimal on the server."""

from datetime import date

from django.db import connection, transaction
from django.db.models import Q, Sum

from apps.company.models import CompanyProfile

from .models import Account, JournalLine
from .money import ZERO, strings


def balances(as_of, start=None):
    start = start or date.min
    qs = JournalLine.objects.filter(journal__status="posted", journal__posting_date__lte=as_of)
    values = (
        qs.values(
            "account_id",
            "account__code",
            "account__name",
            "account__account_type",
            "account__normal_side",
            "account__subtype",
            "account__parent_id",
        )
        .annotate(
            debit=Sum("base_debit", filter=Q(journal__posting_date__gte=start)),
            credit=Sum("base_credit", filter=Q(journal__posting_date__gte=start)),
            previous_debit=Sum("base_debit", filter=Q(journal__posting_date__lt=start)),
            previous_credit=Sum("base_credit", filter=Q(journal__posting_date__lt=start)),
        )
        .order_by("account__code")
    )
    result = []
    for r in values:
        d, c = r["debit"] or ZERO, r["credit"] or ZERO
        opening = (r["previous_debit"] or ZERO) - (r["previous_credit"] or ZERO)
        normal = 1 if r["account__normal_side"] == "debit" else -1
        result.append(
            {
                "account_id": r["account_id"],
                "code": r["account__code"],
                "name": r["account__name"],
                "account_type": r["account__account_type"],
                "subtype": r["account__subtype"],
                "parent_id": r["account__parent_id"],
                "normal_side": r["account__normal_side"],
                "debit": d,
                "credit": c,
                "raw_opening": opening,
                "raw_balance": opening + d - c,
                "opening": opening * normal,
                "balance": (opening + d - c) * normal,
                "movement": (d - c) * normal,
            }
        )
    return result


def hierarchy(rows):
    """Add visual subtotals after calculating report totals, never as extra postings."""
    accounts = {a.pk: a for a in Account.objects.all()}
    grouped = {r["account_id"]: {**r, "is_summary": False} for r in rows}
    fields = (
        "debit",
        "credit",
        "raw_opening",
        "raw_balance",
        "debit_balance",
        "credit_balance",
        "report_amount",
    )
    for row in rows:
        parent = row["parent_id"]
        while parent:
            a = accounts[parent]
            if parent not in grouped:
                grouped[parent] = {
                    "account_id": a.pk,
                    "code": a.code,
                    "name": a.name,
                    "account_type": a.account_type,
                    "normal_side": a.normal_side,
                    "subtype": a.subtype,
                    "parent_id": a.parent_id,
                    "is_summary": True,
                    **{f: ZERO for f in fields},
                }
            for field in fields:
                grouped[parent][field] += row.get(field, ZERO)
            parent = a.parent_id
    for row in grouped.values():
        sign = 1 if row["normal_side"] == "debit" else -1
        row.update(
            balance=row["raw_balance"] * sign,
            opening=row["raw_opening"] * sign,
            movement=(row["debit"] - row["credit"]) * sign,
        )
        path, parent = [row["code"]], row["parent_id"]
        while parent:
            a = accounts[parent]
            path.insert(0, a.code)
            parent = a.parent_id
        row["depth"] = len(path) - 1
        row["_path"] = path
    ordered = sorted(grouped.values(), key=lambda row: row["_path"])
    for row in ordered:
        row.pop("_path")
    return ordered


@transaction.atomic
def report(which, start, end):
    from apps.core.exceptions import BusinessRuleViolation

    # The shared write lock keeps multi-query report families on one ledger snapshot.
    company = CompanyProfile.objects.select_for_update().filter(pk=1).first()
    if company is None:
        raise BusinessRuleViolation("Set up the company profile first.", code="company_required")
    year_start = date(
        end.year if end.month >= company.fiscal_year_start_month else end.year - 1,
        company.fiscal_year_start_month,
        1,
    )
    # One aggregated statement contains opening and date-range activity, so it
    # observes one financial snapshot even while another connection posts.
    rows = balances(end, year_start if which == "bs" else start)
    out = {
        "report": which,
        "from": start,
        "to": end,
        "base_currency": company.base_currency,
        "rows": [],
    }
    if which == "tb":
        out["rows"] = [
            {
                **r,
                "debit_balance": max(r["raw_balance"], ZERO),
                "credit_balance": max(-r["raw_balance"], ZERO),
            }
            for r in rows
        ]
        d = sum((r["debit_balance"] for r in out["rows"]), ZERO)
        c = sum((r["credit_balance"] for r in out["rows"]), ZERO)
        out.update(total_debits=d, total_credits=c, difference=d - c, balanced=d == c)
    elif which == "pnl":
        out["rows"] = [r for r in rows if r["account_type"] in ("revenue", "expense")]
        for r in out["rows"]:
            r["report_amount"] = (
                (r["credit"] - r["debit"])
                if r["account_type"] == "revenue"
                else (r["debit"] - r["credit"])
            )
        revenue = sum(
            (r["credit"] - r["debit"] for r in rows if r["account_type"] == "revenue"), ZERO
        )
        expenses = sum(
            (r["debit"] - r["credit"] for r in rows if r["account_type"] == "expense"), ZERO
        )
        cost_of_sales = sum(
            (r["debit"] - r["credit"] for r in out["rows"] if r["subtype"] == "Cost of sales"), ZERO
        )
        out.update(
            revenue=revenue,
            expenses=expenses,
            cost_of_sales=cost_of_sales,
            other_expenses=expenses - cost_of_sales,
            gross_profit=revenue - cost_of_sales,
            net_profit=revenue - expenses,
        )
    elif which == "bs":
        out["rows"] = [r for r in rows if r["account_type"] in ("asset", "liability", "equity")]
        for r in out["rows"]:
            r["report_amount"] = (
                r["raw_balance"] if r["account_type"] == "asset" else -r["raw_balance"]
            )
        assets = sum((r["raw_balance"] for r in rows if r["account_type"] == "asset"), ZERO)
        liabilities = sum(
            (-r["raw_balance"] for r in rows if r["account_type"] == "liability"), ZERO
        )
        posted_equity = sum(
            (-r["raw_balance"] for r in rows if r["account_type"] == "equity"), ZERO
        )
        prior = sum(
            (-r["raw_opening"] for r in rows if r["account_type"] in ("revenue", "expense")), ZERO
        )
        current = sum(
            (r["credit"] - r["debit"] for r in rows if r["account_type"] in ("revenue", "expense")),
            ZERO,
        )
        equity = posted_equity + prior + current
        out.update(
            assets=assets,
            liabilities=liabilities,
            posted_equity=posted_equity,
            prior_earnings=prior,
            current_earnings=current,
            equity=equity,
            difference=assets - liabilities - equity,
            balanced=assets == liabilities + equity,
        )
    elif which == "cf":
        bank_ids = Account.objects.filter(bank_account__isnull=False).values_list("id", flat=True)
        cash_rows = [r for r in rows if r["account_id"] in bank_ids]
        # Aggregate by journal to eliminate movement between two company cash accounts.
        movements = (
            JournalLine.objects.filter(
                account_id__in=bank_ids,
                journal__status="posted",
                journal__posting_date__range=(start, end),
            )
            .values("journal_id", "journal__kind")
            .annotate(d=Sum("base_debit"), c=Sum("base_credit"))
        )
        receipts = payments = transfers = fx = ZERO
        for m in movements:
            net = m["d"] - m["c"]
            if m["journal__kind"] == "transfer":
                fx += net
                transfers += min(m["d"], m["c"])
            elif net > 0:
                receipts += net
            else:
                payments -= net
        opening = sum((r["raw_opening"] for r in cash_rows), ZERO)
        closing = sum((r["raw_balance"] for r in cash_rows), ZERO)
        out.update(
            rows=cash_rows,
            opening=opening,
            receipts=receipts,
            payments=payments,
            internal_transfers=transfers,
            transfer_fx_effect=fx,
            closing=closing,
            difference=closing - opening - receipts + payments - fx,
            classification="Cash movement; statutory cash-flow classification arrives in Phase 6.",
        )
        from apps.reporting.cash_flow import classified_statement

        out = classified_statement(out, start, end)
    else:
        out["rows"] = rows
    out["rows"] = hierarchy(out["rows"])
    return strings(out)


def ledger(account_id, start, end, *, search="", page=1, page_size=25):
    account = Account.objects.get(pk=account_id)
    sign = 1 if account.normal_side == "debit" else -1
    # Windowing precedes search and pagination. Opening, full-range totals and
    # running balances share one SQL snapshot; Python only receives the page.
    with connection.cursor() as cur:
        cur.execute(
            """
            WITH RECURSIVE subtree AS (
                SELECT id FROM accounting_account WHERE id = %(account)s
                UNION ALL SELECT a.id FROM accounting_account a JOIN subtree s ON a.parent_id=s.id
            ), lines AS (
                SELECT l.id, l.position, l.journal_id::text, j.posting_date AS date, j.number,
                    COALESCE(NULLIF(l.description,''), j.description) AS description,
                    j.source_type AS source, l.base_debit AS debit, l.base_credit AS credit,
                    l.currency, l.debit AS native_debit, l.credit AS native_credit,
                    SUM(l.base_debit-l.base_credit) OVER (
                        ORDER BY j.posting_date, j.number, l.position, l.id ROWS UNBOUNDED PRECEDING
                    ) * %(sign)s AS balance
                FROM accounting_journalline l JOIN accounting_journalentry j ON j.id=l.journal_id
                WHERE l.account_id IN (SELECT id FROM subtree)
                    AND j.status='posted' AND j.posting_date<=%(end)s
            ), summary AS (
                SELECT COALESCE(SUM(debit-credit) FILTER (WHERE date<%(start)s),0)
                       *%(sign)s AS opening,
                    COALESCE(SUM(debit) FILTER (WHERE date>=%(start)s),0) AS debit,
                    COALESCE(SUM(credit) FILTER (WHERE date>=%(start)s),0) AS credit,
                    COALESCE(SUM(debit-credit),0)*%(sign)s AS closing FROM lines
            ), matched AS (
                SELECT * FROM lines WHERE date>=%(start)s AND (
                    %(search)s='' OR strpos(lower(number||' '||description||' '||source),
                                           lower(%(search)s))>0
                )
            ), page_rows AS (
                SELECT * FROM matched ORDER BY date, number, position, id
                LIMIT %(size)s OFFSET %(offset)s
            )
            SELECT summary.*, (SELECT COUNT(*) FROM matched), COALESCE((
                SELECT jsonb_agg(jsonb_build_object(
                    'id', id, 'journal_id', journal_id, 'date', date, 'number', number,
                    'description', description, 'source', source, 'debit', debit::text,
                    'credit', credit::text, 'balance', balance::text, 'currency', currency,
                    'native_debit', native_debit::text, 'native_credit', native_credit::text
                ) ORDER BY date,number,position,id) FROM page_rows
            ), '[]'::jsonb) FROM summary
        """,
            {
                "account": account.pk,
                "sign": sign,
                "start": start,
                "end": end,
                "search": search,
                "size": page_size,
                "offset": (page - 1) * page_size,
            },
        )
        opening, debit, credit, closing, count, rows = cur.fetchone()
    if isinstance(rows, str):
        import json

        rows = json.loads(rows)
    return strings(
        {
            "account": {
                "id": account.pk,
                "code": account.code,
                "name": account.name,
                "normal_side": account.normal_side,
            },
            "opening": opening,
            "debit": debit,
            "credit": credit,
            "closing": closing,
            "count": count,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (count + page_size - 1) // page_size),
            "results": rows,
        }
    )
