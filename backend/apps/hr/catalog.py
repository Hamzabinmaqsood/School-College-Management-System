HR_PERMISSIONS = {
    "Staff": {
        "view": "accounts.view_staff",
        "add": "accounts.add_employee",
        "update": "accounts.change_employee",
        "manage": "accounts.manage_hr_registry",
        "export": "accounts.export_hr",
    },
    "Teachers": {"view": "accounts.view_teachers"},
    "Employee Documents": {
        "view": "accounts.view_employee_documents",
        "manage": "accounts.manage_employee_documents",
    },
    "Staff Attendance": {
        "view": "accounts.view_staff_attendance",
        "add": "accounts.mark_staff_attendance",
        "update": "accounts.correct_staff_attendance",
    },
    "Employee Leave": {
        "view": "accounts.view_staff_leave",
        "add": "accounts.request_staff_leave",
        "approve": "accounts.approve_staff_leave",
    },
    "Payroll": {
        "update": "accounts.correct_payroll",
        "view": "accounts.view_payroll",
        "add": "accounts.generate_payroll",
        "submit": "accounts.submit_payroll",
        "verify": "accounts.review_payroll",
        "approve": "accounts.approve_payroll",
        "manage": "accounts.finalize_payroll",
        "print": "accounts.print_payslip",
        "export": "accounts.export_payroll",
    },
    "Salary Structure Approvals": {
        "view": "accounts.view_salary_structure_approvals",
        "submit": "accounts.submit_salary_structure",
        "approve": "accounts.approve_salary_structure",
        "manage": "accounts.activate_salary_structure",
    },
    "Compensation": {
        "view": "accounts.view_salary_setup",
        "manage": "accounts.manage_salary_setup",
        "approve": "accounts.approve_salary_advance",
        "update": "accounts.pay_salary",
    },
}
