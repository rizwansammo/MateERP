import { type Page, expect, test } from '@playwright/test';
import { savedPreference } from './support';

const sidebarWidth = (page: Page) =>
  page.getByTestId('sidebar').evaluate((el) => el.getBoundingClientRect().width);

test.describe('application shell', () => {
  test('root opens the dashboard and the boot splash clears', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(page.getByTestId('boot-splash')).toHaveCount(0);
    await expect(page.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeVisible();
  });

  test('applies the approved design tokens', async ({ page }) => {
    await page.goto('/dashboard');
    const sidebar = page.getByTestId('sidebar');
    await expect(sidebar).toHaveCSS('background-color', 'rgb(10, 15, 22)');
    expect(await sidebarWidth(page)).toBe(264);
    await expect(page.getByRole('banner')).toHaveCSS('height', '56px');
    await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(237, 240, 244)');
    await expect(page.getByRole('link', { name: 'Dashboard' })).toHaveCSS(
      'background-color',
      'rgba(0, 176, 240, 0.13)',
    );
  });

  test('sidebar collapses to 64px, persists, and expands to 264px', async ({ page }) => {
    await page.goto('/dashboard');
    const compact = await savedPreference(page, () => page.getByRole('button', { name: 'Collapse sidebar' }).click());
    expect(compact.preferences.sidebar).toBe('compact');
    await expect.poll(() => sidebarWidth(page)).toBe(64);

    await page.reload();
    await expect.poll(() => sidebarWidth(page)).toBe(64);

    const full = await savedPreference(page, () => page.getByRole('button', { name: 'Expand sidebar' }).click());
    expect(full.preferences.sidebar).toBe('full');
    await expect.poll(() => sidebarWidth(page)).toBe(264);
  });

  test('theme switches to dark and persists across reloads', async ({ page }) => {
    await page.goto('/dashboard');
    const dark = await savedPreference(page, () => page.getByRole('button', { name: 'Switch to dark mode' }).click());
    expect(dark.preferences.theme).toBe('dark');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(6, 9, 13)');

    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    const light = await savedPreference(page, () => page.getByRole('button', { name: 'Switch to light mode' }).click());
    expect(light.preferences.theme).toBe('light');
    await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(237, 240, 244)');
  });

  test('accounting navigation opens working Phase 3 pages', async ({ page }) => {
    await page.goto('/dashboard');
    await page.getByRole('link', { name: /banking & accounting/i }).click();
    await expect(page).toHaveURL(/\/banking\/overview$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Banking & accounting overview' })).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Breadcrumb' })).toContainText('Banking & Accounting');

    await page.getByRole('link', { name: 'Journal Entries' }).click();
    await expect(page).toHaveURL(/\/banking\/journals$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Journal entries' })).toBeVisible();
  });

  test('unknown routes return 404', async ({ page }) => {
    const response = await page.goto('/payroll');
    expect(response?.status()).toBe(404);
    await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible();
  });

  test('narrow screens use an off-canvas sidebar', async ({ page }) => {
    await page.setViewportSize({ width: 820, height: 900 });
    await page.goto('/dashboard');
    const sidebar = page.getByTestId('sidebar');
    await expect(sidebar).not.toBeInViewport();

    await page.getByRole('button', { name: 'Open navigation' }).click();
    await expect(sidebar).toBeInViewport();
    await page.keyboard.press('Escape');
    await expect(sidebar).not.toBeInViewport();
  });
});

test.describe('backend integration', () => {
  test('the API proxy reaches the Django health endpoint', async ({ request }) => {
    const response = await request.get('/api/v1/health/');
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body).toMatchObject({ status: 'ok', service: 'mateerp-backend' });
    expect(response.headers()['x-request-id']).toBeTruthy();
  });

  test('unknown API routes keep the standard error envelope through the proxy', async ({ request }) => {
    const response = await request.get('/api/v1/does-not-exist/');
    expect(response.status()).toBe(404);
    expect((await response.json()).error.code).toBe('not_found');
  });

  test('the dashboard shows live backend and database status', async ({ page }) => {
    await page.goto('/dashboard');
    const stats = page.getByTestId('health-stats');
    await expect(stats).toContainText('Operational');
    await expect(stats).toContainText('Connected');
    await expect(stats).toContainText('0.6.0');
  });
});
