"""Object-level read authorisation for private files.

Authentication alone never grants access. Each purpose has its own rule,
evaluated against where the file is *currently referenced*. Apps that
reference files register a resolver (see ``register_reference_resolver``)
from their AppConfig.ready(), so this module needs no imports from them.
Anything not explicitly allowed is denied.
"""

from collections.abc import Callable

from .models import FilePurpose, StoredFile

# A resolver returns labels such as {"company_logo", "branding_version"} for
# the places that reference the given file id.
ReferenceResolver = Callable[[StoredFile], set[str]]
_resolvers: list[ReferenceResolver] = []


def register_reference_resolver(resolver: ReferenceResolver) -> None:
    if resolver not in _resolvers:
        _resolvers.append(resolver)


def references(stored: StoredFile) -> set[str]:
    found: set[str] = set()
    for resolver in _resolvers:
        found |= resolver(stored)
    return found


def can_read(user, stored: StoredFile) -> bool:
    from apps.accounts.authorization import get_permission_codes

    if user is None or not user.is_authenticated or not user.is_active:
        return False
    perms = get_permission_codes(user)
    refs = references(stored)

    if stored.purpose == FilePurpose.COMPANY_LOGO:
        # The live company logo (and logos in branding history) appears in the
        # application chrome for every signed-in user.
        if refs:
            return True
        return bool({"branding.manage", "company.edit"} & perms)

    if stored.purpose in (FilePurpose.BRANDING_SIGNATURE, FilePurpose.BRANDING_SEAL):
        # Signatures and seals are sensitive document-authentication assets.
        return "branding.manage" in perms

    return False
