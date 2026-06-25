from django.contrib import admin

from apps.finance.models import (
    BankAccount,
    BankStatement,
    BankStatementLine,
    PeriodClose,
    PaymentBatch,
    Reconciliation,
    ScheduledPayment,
    SpendingAlert,
    Transaction,
    Vendor,
)

admin.site.register(Transaction)
admin.site.register(BankAccount)
admin.site.register(Vendor)
admin.site.register(SpendingAlert)
admin.site.register(PaymentBatch)
admin.site.register(PeriodClose)
admin.site.register(ScheduledPayment)
admin.site.register(BankStatement)
admin.site.register(BankStatementLine)
admin.site.register(Reconciliation)
