BROAD = "accounts.scope_all_examinations"
EXAM_PERMISSIONS = {
    "Examinations": {
        "view": "accounts.view_examinations",
        "manage": "accounts.manage_examinations",
        "verify": BROAD,
    },
    "Exam Configuration": {
        "manage": "accounts.configure_exam_assessments",
        "update": "accounts.manage_exam_schedule",
        "add": "accounts.manage_exam_grading",
    },
    "Exam Marks": {
        "view": "accounts.view_exam_marks",
        "add": "accounts.enter_exam_marks",
        "update": "accounts.update_exam_marks",
        "submit": "accounts.submit_exam_marks",
        "verify": "accounts.verify_exam_marks",
    },
    "Exam Results": {
        "view": "accounts.view_student_results",
        "details": "accounts.view_class_results",
        "approve": "accounts.approve_exam_results",
        "publish": "accounts.publish_exam_results",
        "update": "accounts.correct_exam_results",
        "print": "accounts.print_exam_results",
        "export": "accounts.export_exam_results",
        "manage": "accounts.view_exam_analytics",
    },
}
