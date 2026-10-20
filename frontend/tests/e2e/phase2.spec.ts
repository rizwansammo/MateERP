import { type Browser, type Page, expect, test } from '@playwright/test';

import { apiPost, backend, csrfHeaders, djangoShell, ensureUser, fillLogin, login, pngBuffer, signedInPage, strongPassword } from './support';

/*
 * Phase 2 acceptance scenarios A–K against the live stack, through the
 * browser origin (localhost:3100) and the Next.js proxy — real session
 * cookies and real CSRF. Runs serially; state builds on earlier scenarios.
 */
test.describe.configure({ mode: 'serial' });

const RUN = Date.now().toString(36);

/** Audit row with the given action label and record text (search is debounced). */
function auditRow(page: Page, action: string, record: string) {
  return page.getByRole('row').filter({ hasText: action }).filter({ hasText: record });
}

async function freshContext(browser: Browser) {
  return browser.newContext({ storageState: { cookies: [], origins: [] }, viewport: { width: 1440, height: 900 } });
}

async function setNewPassword(page: Page, current: string, next: string) {
  await expect(page).toHaveURL(/\/account\/password/);
  await page.getByLabel(/Temporary password|Current password/).fill(current);
  await page.getByLabel('New password', { exact: true }).fill(next);
  await page.getByLabel('Confirm new password').fill(next);
  await page.getByRole('button', { name: 'Save new password' }).click();
  await expect(page).toHaveURL(/\/dashboard/);
}

/** Create a user through the UI and return the one-time temporary password. */
async function createUserViaUi(page: Page, username: string, roleName: string): Promise<string> {
  await page.goto('/settings/users');
  await page.getByRole('button', { name: 'Create user' }).click();
  const drawer = page.getByRole('dialog');
  await drawer.getByLabel('First name').fill(username.split('-')[1] ?? username);
  await drawer.getByLabel(/^Username/).fill(username);
  await drawer.getByLabel(/^Email/).fill(`${username}@example.test`);
  await drawer.getByLabel(/^Role/).selectOption({ label: roleName });
  await drawer.getByRole('button', { name: 'Create user' }).click();
  const temp = (await page.getByTestId('temporary-password').textContent())!.trim();
  await page.getByRole('button', { name: 'I have shared it securely' }).click();
  return temp;
}

test('A — initial administrator setup with the documented command', async ({ browser }) => {
  const username = `e2e-boot-${RUN}`;
  const password = strongPassword();
  const out = backend(
    ['python', 'manage.py', 'create_admin', '--no-input', '--username', username, '--email', `${username}@example.test`, '--force-additional'],
    { MATEERP_ADMIN_PASSWORD: password },
  );
  expect(out).toContain(`Administrator '${username}' created`);
  expect(out).not.toContain(password);
  expect(djangoShell(`from apps.accounts.models import User; u=User.objects.get(username="${username}"); print(u.role.is_admin, u.is_active)`)).toBe('True True');

  const context = await freshContext(browser);
  const page = await context.newPage();
  await page.goto('/settings/users');
  await expect(page).toHaveURL(/\/login\?next=%2Fsettings%2Fusers/);
  await fillLogin(page, username, password);
  await expect(page).toHaveURL(/\/settings\/users/);
  await page.goto('/dashboard');
  await expect(page.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeVisible();

  await page.getByRole('button', { name: 'Account menu' }).click();
  await page.getByRole('menuitem', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto('/settings/company');
  await expect(page).toHaveURL(/\/login/);
  await context.close();
});

test('B — session and CSRF protection through the proxy', async ({ browser }) => {
  const context = await freshContext(browser);
  const page = await signedInPage(context, process.env.E2E_ADMIN_USER!, process.env.E2E_ADMIN_PASSWORD!);
  const session = (await context.cookies()).find((c) => c.name === 'mateerp_session')!;
  expect(session.httpOnly).toBe(true);
  expect(session.sameSite).toBe('Lax');

  await page.reload();
  await expect(page.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeVisible();

  const noToken = await page.request.patch('/api/v1/auth/me/', { data: { first_name: 'E2E' }, headers: { Origin: 'http://localhost:3100' } });
  expect(noToken.status()).toBe(403);
  expect((await noToken.json()).error.code).toBe('csrf_failed');
  const forged = await page.request.patch('/api/v1/auth/me/', { data: { first_name: 'E2E' }, headers: { 'X-CSRFToken': 'forged-token-value-000000000000000', Origin: 'http://localhost:3100' } });
  expect(forged.status()).toBe(403);
  const withToken = await page.request.patch('/api/v1/auth/me/', { data: { first_name: 'E2E' }, headers: await csrfHeaders(context) });
  expect(withToken.status()).toBe(200);

  await page.getByRole('button', { name: 'Account menu' }).click();
  await page.getByRole('menuitem', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/login/);

  const replay = await freshContext(browser);
  await replay.addCookies([{ ...session }]);
  const reused = await replay.request.get('http://localhost:3100/api/v1/auth/me/');
  expect(reused.status()).toBe(401);
  const replayPage = await replay.newPage();
  await replayPage.goto('/dashboard');
  await expect(replayPage).toHaveURL(/\/login/);
  await replay.close();
  await context.close();
});

test('C — create a restricted user who completes first sign-in', async ({ page, browser }) => {
  const username = `e2e-viewer-${RUN}`;
  const temp = await createUserViaUi(page, username, 'Viewer');
  await page.getByLabel('Search users').fill(username);
  await expect(page.getByRole('cell', { name: new RegExp(username) })).toBeVisible();

  const context = await freshContext(browser);
  const userPage = await context.newPage();
  await login(userPage, username, temp);
  await setNewPassword(userPage, temp, strongPassword());
  await userPage.goto('/settings/users');
  await expect(userPage.getByText('Access restricted')).toBeVisible();
  expect((await userPage.request.get('/api/v1/users/')).status()).toBe(403);
  await expect(userPage.getByRole('link', { name: /founder finance/i }).getByText('lock')).toBeVisible();
  await context.close();

  await page.goto('/settings/audit');
  await page.getByLabel('Search audit log').fill(username);
  await expect(auditRow(page, 'User created', username)).toBeVisible();
  await expect(auditRow(page, 'Password changed', username)).toBeVisible();
});

test('D — custom role permissions are enforced server-side and change live', async ({ page, browser }) => {
  const roleName = `E2E Auditor ${RUN}`;
  await page.goto('/settings/users');
  await page.getByRole('button', { name: 'New custom role' }).click();
  await page.getByRole('dialog').getByLabel('Role name').fill(roleName);
  await page.getByRole('dialog').getByRole('button', { name: 'Create role' }).click();
  await expect(page.getByRole('cell', { name: new RegExp(roleName) })).toBeVisible();

  await page.goto('/settings/permissions');
  await page.getByRole('switch', { name: `View audit logs for ${roleName}` }).click();
  await page.getByRole('switch', { name: `View company settings for ${roleName}` }).click();
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('switch', { name: `View audit logs for ${roleName}` })).toHaveAttribute('aria-checked', 'true');

  const username = `e2e-auditor-${RUN}`;
  const temp = await createUserViaUi(page, username, `${roleName} (custom)`);
  const context = await freshContext(browser);
  const userPage = await context.newPage();
  await login(userPage, username, temp);
  const password = strongPassword();
  await setNewPassword(userPage, temp, password);

  await userPage.goto('/settings/audit');
  await expect(userPage.getByRole('heading', { level: 1, name: 'Audit log' })).toBeVisible();
  await userPage.goto('/settings/users');
  await expect(userPage.getByText('Access restricted')).toBeVisible();
  const denied = await apiPost(userPage.request, context, '/api/v1/roles/', { name: 'Escalation attempt' });
  expect(denied.status()).toBe(403);

  // Revoke while the user stays signed in: the next request is denied.
  await page.goto('/settings/permissions');
  await page.getByRole('switch', { name: `View audit logs for ${roleName}` }).click();
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('switch', { name: `View audit logs for ${roleName}` })).toHaveAttribute('aria-checked', 'false');
  expect((await userPage.request.get('/api/v1/audit/events/')).status()).toBe(403);
  await userPage.reload();
  await expect(userPage.getByText('Access restricted')).toBeVisible();
  await context.close();
});

test('E — deactivation ends sessions and blocks sign-in', async ({ page, browser }) => {
  const username = `e2e-leaver-${RUN}`;
  const password = strongPassword();
  ensureUser(username, 'accountant', password, 'Leaver');
  const context = await freshContext(browser);
  const userPage = await signedInPage(context, username, password);

  await page.goto('/settings/users');
  await page.getByLabel('Search users').fill(username);
  const row = page.getByRole('row', { name: new RegExp(username) });
  await row.getByRole('button', { name: 'Deactivate' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Deactivate' }).click();
  await expect(row.getByText('Inactive')).toBeVisible();

  expect((await userPage.request.get('/api/v1/auth/me/')).status()).toBe(401);
  await userPage.goto('/dashboard');
  await expect(userPage).toHaveURL(/\/login/);
  await login(userPage, username, password);
  await expect(userPage.getByText('The username or password is incorrect.')).toBeVisible();
  await context.close();

  const me = await (await page.request.get('/api/v1/auth/me/')).json();
  const self = await apiPost(page.request, page.context(), `/api/v1/users/${me.id}/deactivate/`);
  expect(self.status()).toBe(409);

  await page.goto('/settings/audit');
  await page.getByLabel('Search audit log').fill(username);
  await expect(auditRow(page, 'User deactivated', username)).toBeVisible();
});

test('F — company profile persists, logo uploads and a second company is rejected', async ({ page, browser }) => {
  await page.goto('/settings/company');
  const setup = page.getByRole('button', { name: 'Set up company profile' });
  await page.getByText(/Set up your company|Company logo/).first().waitFor();
  if (await setup.isVisible()) {
    await setup.click();
    await page.getByRole('dialog').getByLabel('Display name').fill('NetaMate');
    await page.getByRole('dialog').getByRole('button', { name: 'Create company profile' }).click();
  }
  await page.getByRole('button', { name: 'Edit company profile' }).click();
  const drawer = page.getByRole('dialog');
  await drawer.getByLabel('City').fill(`Dhaka ${RUN}`);
  await drawer.getByLabel('Country').fill('Bangladesh');
  await drawer.getByLabel('Base currency').selectOption('BDT');
  await drawer.getByLabel('Time zone').selectOption('Asia/Dhaka');
  await drawer.getByRole('button', { name: 'Save changes' }).click();
  await expect(drawer).toBeHidden();

  await page.locator('input[type=file]').first().setInputFiles({ name: 'logo.png', mimeType: 'image/png', buffer: pngBuffer() });
  await expect(page.getByText(/^Logo (uploaded|replaced)$/)).toBeVisible();
  await expect(page.getByAltText(/logo/)).toBeVisible();

  await page.reload();
  await expect(page.getByRole('main')).toContainText(`Dhaka ${RUN}`);
  const card = page.getByTestId('company-card');
  await expect(card).toContainText('NetaMate');
  await expect(card).toContainText(`Dhaka ${RUN}`);
  const logoUrl = await card.locator('img').getAttribute('src');
  expect(logoUrl).toMatch(/^\/api\/v1\/files\/.+\/content\/$/);

  const second = await apiPost(page.request, page.context(), '/api/v1/company/', { display_name: 'Second Co' });
  expect(second.status()).toBe(409);
  expect((await second.json()).error.code).toBe('company_exists');

  // The live logo is visible to any signed-in user, never to anonymous visitors.
  expect((await page.request.get(logoUrl!)).status()).toBe(200);
  const anon = await freshContext(browser);
  expect((await anon.request.get(`http://localhost:3100${logoUrl}`)).status()).toBe(401);
  await anon.close();
});

test('G — invoice & receipt branding: edit, preview, save, publish and keep history', async ({ page, browser }) => {
  const versionsBefore = (await (await page.request.get('/api/v1/branding/')).json()).versions as { number: number; published_at: string; invoice_template: string }[];
  await page.goto('/settings/branding');
  await page.getByRole('button', { name: 'Open branding editor' }).click();
  const studio = page.getByRole('dialog', { name: 'Branding editor' });
  await studio.getByRole('radio', { name: /Ledger/ }).click();
  await expect(studio.locator('[data-findoc="invoice"]').last()).toHaveAttribute('data-template', 'ledger');
  await studio.getByLabel('Brand colour', { exact: true }).fill('#1F2937');
  await studio.getByLabel('Payment instructions').fill(`Example Bank · Account 0001 (${RUN})`);
  await expect(studio.locator('[data-findoc="invoice"]').last()).toContainText(`Account 0001 (${RUN})`);
  await studio.getByLabel('Signatory name').fill('E2E Signatory');
  await studio.locator('input[type=file]').nth(1).setInputFiles({ name: 'signature.png', mimeType: 'image/png', buffer: pngBuffer() });
  await expect(studio.getByAltText('Signature image')).toBeVisible();
  await studio.getByRole('radio', { name: 'Stamp editor' }).click();
  await studio.getByLabel('Top arc text').fill('NETAMATE');
  await studio.getByRole('radio', { name: 'Receipt' }).click();
  await expect(studio.locator('[data-findoc="receipt"]')).toContainText('OFFICIAL MONEY RECEIPT');
  await expect(studio.getByRole('img', { name: /Company seal: NETAMATE/ }).last()).toBeVisible();

  await studio.getByRole('button', { name: 'Save draft' }).click();
  await expect(studio.getByText('Draft saved · not yet published')).toBeVisible();
  await studio.getByRole('button', { name: 'Publish' }).click();
  await page.getByLabel('Version label (optional)').fill(`E2E ${RUN}`);
  await page.getByRole('dialog', { name: 'Publish branding' }).getByRole('button', { name: 'Publish' }).click();
  await expect(studio).toBeHidden();

  await page.reload();
  const current = page.getByRole('row', { name: new RegExp(`E2E ${RUN}`) });
  await expect(current.getByText('Current')).toBeVisible();
  // Every earlier version is still there, unchanged; exactly one new version was added.
  const versionsAfter = (await (await page.request.get('/api/v1/branding/')).json()).versions as typeof versionsBefore;
  expect(versionsAfter).toHaveLength(versionsBefore.length + 1);
  expect(versionsAfter.slice(1)).toEqual(versionsBefore);
  if (versionsBefore.length) await expect(page.getByText('Historical').first()).toBeVisible();

  // A previous version (if any) is preserved and viewable read-only.
  await current.getByRole('button', { name: 'Preview' }).click();
  const viewer = page.getByRole('dialog', { name: 'Branding version preview' });
  await expect(viewer.locator('[data-findoc="invoice"]')).toHaveAttribute('data-template', 'ledger');
  await viewer.getByRole('button', { name: 'Close' }).click();

  // Signatures are sensitive: a viewer cannot fetch them even with the URL.
  const version = await (await page.request.get('/api/v1/branding/')).json();
  const signatureUrl = version.current.signature_url as string;
  expect((await page.request.get(signatureUrl)).status()).toBe(200);
  const viewerName = `e2e-v2-${RUN}`;
  const pw = strongPassword();
  ensureUser(viewerName, 'viewer', pw);
  const ctx = await freshContext(browser);
  const viewerPage = await signedInPage(ctx, viewerName, pw);
  expect((await viewerPage.request.get(signatureUrl)).status()).toBe(404);
  await ctx.close();

  await page.goto('/settings/audit');
  await page.getByLabel('Search audit log').fill('branding');
  await expect(page.getByRole('cell', { name: 'Branding published' }).first()).toBeVisible();
});

test('H — optional modules hide from navigation and stay honest', async ({ page }) => {
  await page.goto('/settings/modules');
  const toggle = page.getByRole('switch', { name: 'Inventory & Warehouse module' });
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-checked', 'false');
  await expect(page.getByRole('link', { name: /inventory & warehouse/i })).toBeHidden();
  await page.reload();
  await expect(page.getByRole('switch', { name: 'Inventory & Warehouse module' })).toHaveAttribute('aria-checked', 'false');
  await page.goto('/inventory/items');
  await expect(page.getByText(/is disabled/)).toBeVisible();

  await page.goto('/settings/modules');
  await page.getByRole('switch', { name: 'Inventory & Warehouse module' }).click();
  await expect(page.getByRole('link', { name: /inventory & warehouse/i })).toBeVisible();
  await page.goto('/inventory/items');
  await expect(page.getByTestId('planned-notice')).toContainText('Phase 6');

  await page.goto('/settings/modules');
  await expect(page.getByText('Mandatory').first()).toBeVisible();
  const core = await page.request.put('/api/v1/modules/accounting/', { data: { enabled: false }, headers: await csrfHeaders(page.context()) });
  expect(core.status()).toBe(404);
});

test('I — approval rule gates branding publication', async ({ page, browser }) => {
  await page.goto('/settings/approvals');
  await page.getByRole('row', { name: /Sensitive administrative changes/ }).getByRole('button', { name: 'Edit' }).click();
  const drawer = page.getByRole('dialog');
  await drawer.getByRole('checkbox', { name: 'Approval required' }).click();
  await drawer.getByLabel('Designated approver role').selectOption({ label: 'Finance Manager' });
  await drawer.getByRole('button', { name: 'Save rule' }).click();
  await expect(page.getByRole('row', { name: /Sensitive administrative changes/ }).getByText('Required')).toBeVisible();

  await page.goto('/settings/branding');
  await page.getByRole('button', { name: 'Open branding editor' }).click();
  const studio = page.getByRole('dialog', { name: 'Branding editor' });
  await studio.getByLabel('Footer text').fill(`Approved footer ${RUN}`);
  await studio.getByRole('button', { name: 'Submit for approval' }).click();
  await page.getByLabel('Note for the approver').fill('E2E approval check');
  await page.getByRole('dialog', { name: 'Submit branding for approval' }).getByRole('button', { name: 'Submit for approval' }).click();
  await studio.getByRole('button', { name: 'Close' }).click();
  await page.reload();
  await expect(page.getByText(/is waiting for approval/)).toBeVisible();

  const pending = await (await page.request.get('/api/v1/approvals/requests/?status=pending')).json();
  const requestId = pending.results[0].id as number;
  // The requester cannot approve their own request.
  const self = await apiPost(page.request, page.context(), `/api/v1/approvals/requests/${requestId}/approve/`, { reason: '' });
  expect(self.status()).toBe(403);
  // Nor can an unrelated role.
  const viewerName = `e2e-v3-${RUN}`;
  const vpw = strongPassword();
  ensureUser(viewerName, 'viewer', vpw);
  const vctx = await freshContext(browser);
  const vpage = await signedInPage(vctx, viewerName, vpw);
  expect((await apiPost(vpage.request, vctx, `/api/v1/approvals/requests/${requestId}/approve/`, { reason: '' })).status()).toBe(403);
  await vctx.close();

  const fmName = `e2e-fm-${RUN}`;
  const fpw = strongPassword();
  ensureUser(fmName, 'finance_manager', fpw, 'Fiona');
  const fctx = await freshContext(browser);
  const fpage = await signedInPage(fctx, fmName, fpw);
  await expect(fpage.getByRole('button', { name: /Notifications \(1 pending approvals\)/ })).toBeVisible();
  await fpage.goto('/settings/approvals');
  await fpage.getByRole('button', { name: 'Approve' }).first().click();
  await fpage.getByLabel('Comment (optional)').fill('Looks right');
  await fpage.getByRole('dialog').getByRole('button', { name: 'Approve' }).click();
  await expect(fpage.getByText('Nothing waiting for approval.')).toBeVisible();
  await fctx.close();

  await page.goto('/settings/branding');
  await expect(page.getByText(/is waiting for approval/)).toBeHidden();
  const overview = await (await page.request.get('/api/v1/branding/')).json();
  expect(overview.current.config.footer_text).toBe(`Approved footer ${RUN}`);
  expect(overview.versions[0].approved).toBe(true);

  // Reset the rule so later runs publish directly.
  await page.request.patch('/api/v1/approvals/policies/admin_changes/', { data: { is_required: false, approver_role: null }, headers: await csrfHeaders(page.context()) });
});

test('J — security events are audited without secrets', async ({ page, browser }) => {
  const ctx = await freshContext(browser);
  const p = await ctx.newPage();
  const secret = `Wrong-${RUN}-password`;
  await login(p, `e2e-nobody-${RUN}`, secret);
  await expect(p.getByText('The username or password is incorrect.')).toBeVisible();
  await ctx.close();

  await page.goto('/settings/audit');
  await page.getByRole('radio', { name: 'Auth' }).click();
  await page.getByLabel('Outcome').selectOption('failure');
  const row = page.getByRole('row', { name: /Sign-in failed/ }).first();
  await expect(row).toBeVisible();
  await row.click();
  const detail = page.getByRole('dialog');
  await expect(detail).toContainText('unknown identifier');
  await expect(detail).not.toContainText(secret);
  await expect(detail).not.toContainText(`e2e-nobody-${RUN}`);
  await detail.getByRole('button', { name: 'Close' }).last().click();

  const all = await (await page.request.get('/api/v1/audit/events/?page_size=100')).text();
  expect(all).not.toContain(secret);
  expect(all).not.toContain(process.env.E2E_ADMIN_PASSWORD!);

  const viewerName = `e2e-v4-${RUN}`;
  const pw = strongPassword();
  ensureUser(viewerName, 'viewer', pw);
  const vctx = await freshContext(browser);
  const vpage = await signedInPage(vctx, viewerName, pw);
  expect((await vpage.request.get('/api/v1/audit/events/')).status()).toBe(403);
  await vpage.goto('/settings/audit');
  await expect(vpage.getByText('Access restricted')).toBeVisible();
  await vctx.close();
});

test('K — authentication and settings screens keep the MateERP design system', async ({ page, browser }) => {
  const ctx = await freshContext(browser);
  const lp = await ctx.newPage();
  await lp.goto('/login');
  await expect(lp.getByRole('img', { name: 'MateERP' })).toBeVisible();
  await expect(lp.getByRole('button', { name: 'Sign in' })).toHaveCSS('border-radius', '0px');
  await expect(lp.getByLabel('Username or email')).toHaveCSS('height', '34px');
  await lp.evaluate(() => { document.documentElement.dataset.theme = 'dark'; });
  await expect(lp.locator('body')).toHaveCSS('background-color', 'rgb(6, 9, 13)');
  await ctx.close();

  await page.goto('/settings/users');
  await expect(page.getByTestId('sidebar')).toHaveCSS('background-color', 'rgb(10, 15, 22)');
  await expect(page.getByRole('banner')).toHaveCSS('height', '56px');
  await expect(page.getByRole('button', { name: 'Create user' })).toHaveCSS('border-radius', '0px');
  await expect(page.getByRole('button', { name: 'Create user' })).toHaveCSS('height', '34px');
  await page.getByRole('button', { name: 'Create user' }).click();
  await expect(page.getByRole('dialog')).toHaveCSS('width', '560px');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toBeHidden();
});
