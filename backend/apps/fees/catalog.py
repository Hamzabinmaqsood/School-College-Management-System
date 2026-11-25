FEE_PERMISSIONS = {
    "Fees": {"view": "accounts.view_fees", "manage": "accounts.manage_fee_settings"},
    "Fee Categories": {"view": "fees.view_feecategory", "manage": "fees.change_feecategory"},
    "Fee Structures": {"view": "fees.view_feestructure", "manage": "fees.change_feestructure"},
    "Student Fees": {
        "view": "fees.view_studentfeeassignment",
        "manage": "fees.change_studentfeeassignment",
    },
    "Fee Concessions": {
        "view": "fees.view_studentconcession",
        "manage": "fees.change_studentconcession",
        "approve": "accounts.approve_fee_concession",
    },
    "Fee Invoices": {
        "view": "fees.view_feeinvoice",
        "add": "accounts.generate_fee_invoices",
        "suspend": "accounts.void_fee_invoice",
        "print": "accounts.print_fee_challan",
    },
    "Fee Payments": {
        "view": "fees.view_feepayment",
        "add": "accounts.collect_fees",
        "suspend": "accounts.reverse_fee_payment",
        "print": "accounts.print_fee_receipt",
    },
    "Fee Adjustments": {
        "view": "fees.view_feeadjustment",
        "manage": "accounts.manage_fee_adjustments",
        "approve": "accounts.approve_fee_adjustment",
        "verify": "accounts.approve_fee_write_off",
    },
    "Fee Refunds": {"view": "fees.view_feerefund", "approve": "accounts.approve_fee_refund"},
    "Financial Reports": {
        "view": "accounts.view_fee_reports",
        "export": "accounts.export_fee_reports",
    },
}
