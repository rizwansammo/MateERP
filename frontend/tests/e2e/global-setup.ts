import { backend, djangoShell, ensureUser, strongPassword } from './support';

/*
 * Prepares only the guarded, isolated browser-test backend for a run:
 *  - an e2e administrator with a fresh random password (exported via env to workers),
 *  - cleared sign-in throttling (all browsers share the Docker gateway IP in dev),
 *  - approval and module state reset from previous runs.
 */
export default async function globalSetup() {
  djangoShell('from django.conf import settings; assert settings.MATEERP_ENVIRONMENT == "e2e", "Refusing browser fixtures in the development database"');
  const password = strongPassword();
  ensureUser('e2e-admin', 'administrator', password, 'E2E');
  process.env.E2E_ADMIN_USER = 'e2e-admin';
  process.env.E2E_ADMIN_PASSWORD = password;

  backend(['python', 'manage.py', 'clear_login_locks', '--all']);
  djangoShell(`
from apps.approvals.models import ApprovalPolicy, ApprovalRequest
from django.utils import timezone
ApprovalPolicy.objects.filter(category="admin_changes").update(is_required=False, approver_role=None, allow_self_approval=False)
for r in ApprovalRequest.objects.filter(status="pending"):
    r.status = "cancelled"; r.reviewed_at = timezone.now(); r.save()
from apps.company.models import ModuleSetting
ModuleSetting.objects.update(enabled=True)
print("ok")
`);
}
