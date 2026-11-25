import { defineConfig } from '@playwright/test';
import { join } from 'node:path';

const evidence = process.env.SMS_PHASE09_EVIDENCE;
if (!evidence || !process.env.SMS_PHASE09_FIXTURES || !process.env.SMS_PHASE09_BASE_URL) {
  throw new Error('Start the isolated fixtures using tests/browser/phase09/run.sh.');
}

export default defineConfig({
  testDir: '.',
  testMatch: '**/*.browser.mjs',
  testIgnore: process.env.SMS_PHASE10 || process.env.SMS_PHASE09_APPROVAL || process.env.SMS_PHASE09_LEAVE || process.env.SMS_PHASE09_WORKFLOWS || process.env.SMS_PHASE09_MATRIX === '1' || process.env.SMS_PHASE09_FINANCE || process.env.SMS_PHASE09_TEACHER || process.env.SMS_PHASE09_REVISIONS ? [] : ['**/timetable.browser.mjs', '**/salary-approval.browser.mjs', '**/leave-policy.browser.mjs', '**/workflows.browser.mjs', '**/roles.browser.mjs', '**/finance.browser.mjs', '**/teacher-writes.browser.mjs', '**/revisions.browser.mjs'],
  workers: 1,
  outputDir: join(evidence, 'output'),
  reporter: [['line'], ['json', { outputFile: join(evidence, 'results.json') }]],
  use: {
    baseURL: process.env.SMS_PHASE09_BASE_URL,
    trace: 'off',
    screenshot: 'off',
    video: 'off',
    launchOptions: {
      ...(process.env.SMS_PHASE09_CHROME ? { executablePath: process.env.SMS_PHASE09_CHROME } : {}),
    },
  },
  projects: process.env.SMS_PHASE10 ? [
    { name: 'timetable-' + process.env.SMS_PHASE10, testMatch: '**/timetable.browser.mjs', use: {
      viewport: process.env.SMS_PHASE10 === 'mobile'
        ? { width: 390, height: 844 } : { width: 1440, height: 900 },
    } },
  ] : process.env.SMS_PHASE09_APPROVAL ? [
    { name: 'approval-' + process.env.SMS_PHASE09_APPROVAL, testMatch: '**/salary-approval.browser.mjs', use: {
      viewport: process.env.SMS_PHASE09_APPROVAL === 'mobile'
        ? { width: 390, height: 844 } : { width: 1440, height: 900 },
    } },
  ] : process.env.SMS_PHASE09_LEAVE ? [
    { name: 'leave-' + process.env.SMS_PHASE09_LEAVE, testMatch: '**/leave-policy.browser.mjs', use: {
      viewport: process.env.SMS_PHASE09_LEAVE === 'mobile'
        ? { width: 390, height: 844 } : { width: 1440, height: 900 },
    } },
  ] : process.env.SMS_PHASE09_WORKFLOWS ? [
    { name: 'hr-workflows', testMatch: '**/workflows.browser.mjs', use: {
      viewport: process.env.SMS_PHASE09_WORKFLOWS === 'mobile'
        ? { width: 390, height: 844 } : { width: 1440, height: 900 },
    } },
  ] : process.env.SMS_PHASE09_REVISIONS ? [
    { name: 'revisions-' + process.env.SMS_PHASE09_REVISIONS, testMatch: '**/revisions.browser.mjs', use: {
      viewport: process.env.SMS_PHASE09_REVISIONS === 'mobile' ? { width: 390, height: 844 } : { width: 1440, height: 900 },
    } },
  ] : process.env.SMS_PHASE09_TEACHER ? [
    { name: 'teacher-writes', testMatch: '**/teacher-writes.browser.mjs', use: {
      viewport: process.env.SMS_PHASE09_TEACHER === 'mobile' ? { width: 390, height: 844 } : { width: 1440, height: 900 },
    } },
  ] : process.env.SMS_PHASE09_FINANCE ? [
    { name: 'finance-' + process.env.SMS_PHASE09_FINANCE, testMatch: '**/finance.browser.mjs', use: {
      viewport: process.env.SMS_PHASE09_FINANCE === 'mobile' ? { width: 390, height: 844 } : { width: 1440, height: 900 },
    } },
  ] : process.env.SMS_PHASE09_MATRIX === '1' ? [
    { name: 'role-matrix', testMatch: '**/roles.browser.mjs', use: { viewport: { width: 1440, height: 900 } } },
  ] : [
    { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'mobile', use: { viewport: { width: 390, height: 844 } } },
  ],
});
