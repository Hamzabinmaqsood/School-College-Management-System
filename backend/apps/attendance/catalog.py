ATTENDANCE_PERMISSIONS = {
    "Attendance": {
        "view": "accounts.view_attendance",
        "details": "attendance.view_attendancesession",
        "add": "attendance.add_attendancesession",
        "update": "attendance.change_attendancerecord",
        "verify": "accounts.finalize_attendance",
        "approve": "attendance.add_attendancecorrection",
        "export": "accounts.export_attendance",
        "print": "accounts.print_attendance",
        "manage": "accounts.scope_all_attendance",
    },
    "Attendance History": {"view": "accounts.view_attendance_history"},
    "Student Leave": {
        "view": "attendance.view_studentleaverequest",
        "add": "attendance.add_studentleaverequest",
        "approve": "accounts.review_attendance_leave",
        "suspend": "accounts.cancel_attendance_leave",
    },
    "Attendance Calendar": {
        "view": "attendance.view_attendanceholiday",
        "manage": "accounts.manage_attendance_calendar",
        "verify": "accounts.override_attendance_calendar",
    },
    "Attendance Settings": {"manage": "accounts.manage_attendance_settings"},
    "Teaching Assignments": {"manage": "accounts.manage_teaching_assignments"},
}
