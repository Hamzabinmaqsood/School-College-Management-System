import '@angular/compiler';
import { signal } from '@angular/core';
import { describe, expect, it } from 'vitest';
import { recordForm } from './academic-tools';
import { TimetablePage } from './timetable-page';

function pageForLessonOptions(): TimetablePage {
  return Object.assign(Object.create(TimetablePage.prototype), {
    action: 'entries',
    lessonOptions: signal({
      subjects: [{id:'optional'}],
      teachers: [{id:'teacher'}],
      groups: [{id:'group'}],
    }),
    lessonOptionsLoading: signal(false),
    lessonOptionsError: signal(false),
    form: recordForm([
      {key:'subject',label:'Subject'},
      {key:'teacher',label:'Teacher'},
      {key:'group',label:'Group'},
    ]),
  }) as TimetablePage;
}

describe('Timetable lesson eligibility', () => {
  it('requires an eligible optional group before saving', () => {
    const page = pageForLessonOptions();
    page.form.patchValue({subject:'optional',teacher:'teacher'});
    expect(page.lessonEditorBlocked()).toBe(true);

    page.form.patchValue({group:'group'});
    expect(page.lessonEditorBlocked()).toBe(false);
  });

  it('blocks stale subject, teacher, and group selections', () => {
    const page = pageForLessonOptions();
    page.form.patchValue({subject:'other',teacher:'teacher',group:'group'});
    expect(page.lessonEditorBlocked()).toBe(true);

    page.form.patchValue({subject:'optional',teacher:'other'});
    expect(page.lessonEditorBlocked()).toBe(true);

    page.form.patchValue({teacher:'teacher',group:'other'});
    expect(page.lessonEditorBlocked()).toBe(true);
  });
});
