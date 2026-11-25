ACADEMIC_PERMISSIONS = {
    "Academics": {"view": "accounts.view_academics", "manage": "accounts.manage_admissions_policy"},
    "Academic Sessions": {
        "view": "accounts.view_sessions",
        "add": "academics.add_academicsession",
        "update": "academics.change_academicsession",
    },
    "Classes": {
        "view": "accounts.view_classes",
        "add": "academics.add_academicclass",
        "update": "academics.change_academicclass",
    },
    "Sections": {
        "view": "accounts.view_sections",
        "add": "academics.add_section",
        "update": "academics.change_section",
    },
    "Subjects": {
        "view": "accounts.view_subjects",
        "add": "academics.add_subject",
        "update": "academics.change_subject",
    },
    "Class Subject Assignments": {
        "view": "academics.view_classsubject",
        "add": "academics.add_classsubject",
        "update": "academics.change_classsubject",
    },
    "Students": {
        "view": "accounts.view_students",
        "details": "accounts.view_student_details",
        "add": "students.add_student",
        "update": "students.change_student",
        "export": "accounts.export_students",
        "print": "accounts.print_students",
    },
    "Guardians": {
        "view": "students.view_guardian",
        "add": "students.add_guardian",
        "update": "students.change_guardian",
        "manage": "accounts.manage_guardian_links",
    },
    "Admissions": {
        "view": "accounts.view_admissions",
        "add": "admissions.add_studentenrollment",
        "export": "accounts.export_admissions",
    },
    "Student Documents": {
        "view": "students.view_studentdocument",
        "add": "students.add_studentdocument",
        "suspend": "accounts.archive_student_documents",
    },
    "Promotions and Transfers": {"manage": "accounts.progress_students"},
}
