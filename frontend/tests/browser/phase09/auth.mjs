import { expect } from '@playwright/test';

export async function signIn(page, account) {
  await page.goto('/login');
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  await page.locator('[formcontrolname="username"]').fill(account.username);
  await page.locator('[formcontrolname="password"]').evaluate((element, value) => {
    element.value = value;
    element.dispatchEvent(new Event('input', { bubbles: true }));
  }, account.password);
  const login = page.waitForResponse(response => response.url().endsWith('/api/v1/auth/login/'));
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  expect((await login).status()).toBe(200);
  await expect(page).not.toHaveURL(/\/login$/);
}
