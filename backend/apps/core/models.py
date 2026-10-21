from django.db import models


class IdentifiedRecord(models.Model):
    """Human-readable identity for source records without duplicating stored labels."""

    class Meta:
        abstract = True

    def __str__(self):
        return (
            getattr(self, "name", None)
            or getattr(self, "title", None)
            or f"{self._meta.verbose_name} #{self.pk}"
        )
