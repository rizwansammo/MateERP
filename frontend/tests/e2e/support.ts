import { execFileSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import path from 'node:path';

import { type APIRequestContext, type BrowserContext, type Page, expect } from '@playwright/test';
import type { Preferences } from '../../src/lib/api/types';

/** Appearance is immediate; wait for the account write before reload/teardown. */
export async function savedPreference(page: Page, action: () => Promise<void>) {
  const saved = page.waitForResponse((response) =>
    response.url().endsWith('/api/v1/auth/me/') && response.request().method() === 'PATCH',
  );
  await action();
  const response = await saved;
  expect(response.ok(), await response.text()).toBe(true);
  const body: { preferences: Preferences } = await response.json();
  return body;
}

/*
 * E2E harness helpers. They drive the isolated `mateerp` Docker stack only
 * (docker compose in the repository root) and never touch other projects.
 * Test accounts are prefixed "e2e-"; their passwords are random per run and
 * never written to disk.
 */

const REPO_ROOT = path.resolve(process.cwd(), '..');

export function strongPassword(): string {
  return `E2e-${randomBytes(12).toString('base64url')}`;
}

/** Run a command in the mateerp backend container. */
export function backend(args: string[], env: Record<string, string> = {}): string {
  const envArgs = Object.entries(env).flatMap(([k, v]) => ['-e', `${k}=${v}`]);
  return execFileSync('docker', ['compose', 'exec', '-T', ...envArgs, process.env.MATEERP_TEST_SERVICE ?? 'backend-e2e', ...args], {
    cwd: REPO_ROOT,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  }).trim();
}

export function djangoShell(code: string, env: Record<string, string> = {}): string {
  const out = backend(['python', 'manage.py', 'shell', '-c', code], env);
  return out.split('\n').filter((l) => !l.includes('objects imported automatically')).join('\n').trim();
}

const ENSURE_USER = `
import os
from apps.accounts.models import Role, User
u, _ = User.objects.get_or_create(username=os.environ["U"], defaults={"email": os.environ["U"] + "@example.test"})
u.role = Role.objects.get(key=os.environ["R"])
u.first_name = os.environ.get("F", "")
u.is_active = True
u.must_change_password = False
u.preferences = {}
u.set_password(os.environ["P"])
u.save()
print(u.pk)
`;

/** Test-only: create or reset a user with a role and password (bypasses the UI on purpose). */
export function ensureUser(username: string, roleKey: string, password: string, firstName = ''): number {
  return Number(djangoShell(ENSURE_USER, { U: username, R: roleKey, P: password, F: firstName }));
}

export async function login(page: Page, identifier: string, password: string) {
  await page.goto('/login');
  await fillLogin(page, identifier, password);
}

/** Submit the sign-in form on the current page (keeps any ?next=). */
export async function fillLogin(page: Page, identifier: string, password: string) {
  await page.getByLabel('Username or email').fill(identifier);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
}

export async function signedInPage(context: BrowserContext, identifier: string, password: string): Promise<Page> {
  const page = await context.newPage();
  await login(page, identifier, password);
  await expect(page).toHaveURL(/\/(dashboard|account\/password|settings)/);
  return page;
}

/** Headers for a state-changing API call made with the context's own cookies. */
export async function csrfHeaders(context: BrowserContext): Promise<Record<string, string>> {
  const cookie = (await context.cookies()).find((c) => c.name === 'mateerp_csrftoken');
  return { 'X-CSRFToken': cookie?.value ?? '', Origin: 'http://localhost:3100' };
}

export async function apiPost(request: APIRequestContext, context: BrowserContext, url: string, data?: unknown) {
  return request.post(url, { data, headers: await csrfHeaders(context) });
}

export function pngBuffer(): Buffer {
  // 8×8 opaque cyan PNG (generated with Pillow).
  return Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAAFklEQVR4nGNk2PDhPwMewIRPcvgoAAC1MgKvORAoIAAAAABJRU5ErkJggg==',
    'base64',
  );
}
