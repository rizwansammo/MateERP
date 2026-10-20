"""Shared view plumbing for the commercial modules (sales, billing, purchasing, documents)."""

from django.db.models import Q
from rest_framework import viewsets

from apps.accounts.authorization import IsActiveUser, requires, requires_any
from apps.core.pagination import StandardPagination


def validated(cls, data, **kwargs):
    obj = cls(data=data, **kwargs)
    obj.is_valid(raise_exception=True)
    return dict(obj.validated_data)


def search(qs, request, *fields):
    term = request.query_params.get("search", "").strip()
    if term:
        query = Q()
        for field in fields:
            query |= Q(**{f"{field}__icontains": term})
        qs = qs.filter(query)
    return qs


def sort(qs, request, allowed, default):
    order = request.query_params.get("sort", default)
    return qs.order_by(order if order.lstrip("-") in allowed else default, "-pk")


class DomainViewSet(viewsets.GenericViewSet):
    """Reads need ``finance.view``; unsafe methods also need any of ``write_permissions``.

    Services re-check the exact permission for each action; this is the outer gate.
    """

    permission_classes = [IsActiveUser, requires("finance.view")]
    pagination_class = StandardPagination
    write_permissions: tuple[str, ...] = ()

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.request.method not in ("GET", "HEAD", "OPTIONS") and self.write_permissions:
            permissions.append(requires_any(*self.write_permissions)())
        return permissions

    def respond_list(self, qs, cls=None):
        page = self.paginate_queryset(qs)
        return self.get_paginated_response((cls or self.serializer_class)(page, many=True).data)
