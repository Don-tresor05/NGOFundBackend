from django.contrib import admin

from apps.finance.models import BankAccount, BankStatement, BankStatementLine, Reconciliation, Transaction

admin.site.register(Transaction)
admin.site.register(BankAccount)
admin.site.register(BankStatement)
admin.site.register(BankStatementLine)
admin.site.register(Reconciliation)
