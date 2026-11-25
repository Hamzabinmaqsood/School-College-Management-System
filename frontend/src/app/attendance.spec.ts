import '@angular/compiler';
import { Injector, runInInjectionContext } from '@angular/core';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { describe, expect, it, vi } from 'vitest';
import { AcademicWorkspace } from './academic-tools';
import { AdminApi } from './admin';
import { AttendancePage } from './attendance-page';
import { attendanceMonth } from "./attendance-calendar";
import { AuthService } from './auth';

function fixture() {
  const confirm = vi.fn(async () => true);
  const read = vi.fn(async () => ({broad: false, primary_mode: 'daily', date: '2026-11-21',
    assignments: [{session: 'term', academic_class: 'class', section: null, subject: 'subject'}]}));
  const write = vi.fn();
  const workspace = {refresh: vi.fn(async () => undefined), can: vi.fn(() => true)};
  const injector = Injector.create({providers: [
    {provide: AdminApi, useValue: {read, write, confirm}},
    {provide: AuthService, useValue: {}},
    {provide: AcademicWorkspace, useValue: workspace},
    {provide: ActivatedRoute, useValue: {snapshot: {data: {}, queryParamMap: convertToParamMap({})}}},
  ]});
  const page = runInInjectionContext(injector, () => new AttendancePage());
  return {page, confirm, read, write, workspace};
}

describe('attendance register', () => {
  it("handles leap-year months using the selected civil date", () => {
    expect(attendanceMonth("2024-02")).toEqual({from_date: "2024-02-01", to_date: "2024-02-29"});
    expect(attendanceMonth("")).toBeNull();
  });
  it('requires a period code and builds scope from the assigned group', async () => {
    const {page} = fixture();
    await Promise.resolve();
    expect(page.criteria()).toBeNull();
    page.group = '0';
    expect(page.criteria()).toBeNull();
    page.filter.period = ' P1 ';
    expect(page.criteria()).toEqual({session: 'term', academic_class: 'class', date: '2026-11-21',
      subject: 'subject', period: 'P1', mode: 'period'});
  });

  it('prompts before abandoning local marks and saves with the loaded version', async () => {
    const {page, confirm, write} = fixture();
    const rows = [{id: 'record', student_name: 'Student', status: 'unmarked', remarks: 'Prior note',
      admission_number: 'A1', roll_number: '1', approved_leave: false}];
    const draft = {id: 'register', status: 'draft', date: '2026-11-21', mode: 'daily',
      class_name: 'Class', version: 2, records: rows};
    expect(page.leave()).toBe(true);
    page.bulk(draft);
    expect(page.mark(rows[0]!).status).toBe('present');
    await expect(page.leave()).resolves.toBe(true);
    expect(confirm).toHaveBeenCalledWith('Discard unsaved attendance marks?');
    write.mockResolvedValue({...draft, version: 3});
    await page.save(draft);
    expect(write).toHaveBeenCalledWith('POST', 'attendance/register/save/', {
      version: 2, marks: [{record: 'record', status: 'present', remarks: 'Prior note'}],
    });
    expect(page.edits()).toEqual({});
  });

  it('submits explicit acknowledgement when finalizing with unmarked students', async () => {
    const {page, confirm, write, workspace} = fixture();
    const draft = {id: 'register', status: 'draft', date: '2026-11-21', mode: 'daily', class_name: 'Class',
      version: 5, records: [{id: 'record', student_name: 'Student', status: 'unmarked', remarks: '',
        admission_number: 'A1', roll_number: '', approved_leave: false}]};
    write.mockResolvedValue({...draft, status: 'finalized'});
    await page.finalize(draft);
    expect(confirm).toHaveBeenCalledWith('Finalize with 1 students unmarked?');
    expect(write).toHaveBeenCalledWith('POST', 'attendance/register/finalize/',
      {version: 5, acknowledge_unmarked: true});
    workspace.can.mockReturnValue(false);
    expect(page.can('accounts.finalize_attendance')).toBe(false);
    expect(workspace.can).toHaveBeenCalledWith('attendance', 'accounts.finalize_attendance');
  });
});
