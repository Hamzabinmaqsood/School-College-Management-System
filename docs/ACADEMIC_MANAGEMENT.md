# Academic management

Academic definitions belong to the existing institution. Set up the institution
before opening the academic registry. The application accepts institution-defined
names, codes, categories and calendar dates.

## Sessions and reusable groups

Create an academic session with start and end dates and switch it to Active
before enrollment. **Set current** makes it the one current session at this
institution. Other sessions can remain active for parallel calendars or
preparing the next term. Closing clears the current flag and retains dates,
enrollments, and historical reporting. The application keeps referenced
definitions and offers activation or closure instead of deletion.

Classes have institution-wide codes. Section codes are scoped to their class.
A section definition is reusable across sessions. Capacity and roll numbers
are checked within the session and group. An active section must belong to the
selected active class. PostgreSQL also enforces that relationship for enrollment
rows with a section, using a composite foreign key.

Create subjects in Subjects, then use Class Subject Assignments to link a
mandatory or optional subject to a class. Leave Session blank for a reusable
default, or select a session for a term-specific assignment. Assignments have
unique class, subject, and session keys. Deactivate an obsolete assignment
without changing its class, subject or session.

## Permission and license requirements

The role matrix includes permissions for academic sessions, classes, sections,
subjects, assignments, and the admissions numbering policy. Authorize read
access to the academic lookups that an operator needs for data entry. The
academics feature enables licensed writes to academic definitions and the
numbering policy. The current-session selector and academic edits are audited.

## API and verification

The collection routes are academic-sessions/, classes/, sections/, subjects/,
and class-subjects/ under /api/v1/. The collections support list, retrieve,
create and partial update. Sessions support POST set-current/ on a session ID.
Filter, search and sort options are local to each registry. The application
uses Django pagination and UUIDs for record links.

Use the verification commands in the environment documentation. Run the
suite with --ds=config.settings.development against isolated PostgreSQL to
verify the composite enrollment foreign key and database constraints.

Timetable plans use existing academic sessions, sections and required class
subjects. Eligibility uses effective teaching assignments. Weekly subject
bounds are configured per session and section.

Configure optional-subject teaching groups per session and section from
enrollments already in the academic module. A full-section lesson cannot
overlap any option group. Parallel optional groups must have disjoint
students, teachers and rooms.
