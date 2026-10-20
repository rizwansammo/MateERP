import { expect, test as setup } from '@playwright/test';

import { login } from './support';

export const ADMIN_STATE = 'tests/e2e/.auth/admin.json';

setup('sign in as the e2e administrator', async ({ page }) => {
  await login(page, process.env.E2E_ADMIN_USER!, process.env.E2E_ADMIN_PASSWORD!);
  await expect(page).toHaveURL(/\/dashboard/);
  await page.context().storageState({ path: ADMIN_STATE });
});
