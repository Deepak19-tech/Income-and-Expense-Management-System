from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import Account, AccountTransfer, AuditLog, BillReminder, Budget, Category, ExchangeRate, Expense, Income, RecurringTransaction, SavingsGoal


AUDITED_MODELS = (Account, AccountTransfer, BillReminder, Budget, Category, ExchangeRate, Expense, Income, RecurringTransaction, SavingsGoal)


def _snapshot(instance):
    return {field.name: str(getattr(instance, field.name)) for field in instance._meta.fields if field.name not in ('id', 'user')}


@receiver(pre_save)
def capture_audit_before_save(sender, instance, **kwargs):
    if sender not in AUDITED_MODELS or not instance.pk:
        return
    previous = sender.objects.filter(pk=instance.pk).first()
    if previous:
        instance._audit_before = _snapshot(previous)


@receiver(post_save)
def write_audit_on_save(sender, instance, created, **kwargs):
    if sender not in AUDITED_MODELS:
        return
    AuditLog.objects.create(
        user=instance.user,
        action='created' if created else 'updated',
        object_type=sender.__name__,
        object_id=instance.pk,
        description=f'{sender.__name__} {"created" if created else "updated"}: {instance}',
        before=getattr(instance, '_audit_before', {}),
        after=_snapshot(instance),
    )


@receiver(post_delete)
def write_audit_on_delete(sender, instance, **kwargs):
    if sender not in AUDITED_MODELS:
        return
    AuditLog.objects.create(
        user=instance.user,
        action='deleted',
        object_type=sender.__name__,
        object_id=instance.pk,
        description=f'{sender.__name__} deleted: {instance}',
        before=_snapshot(instance),
    )
