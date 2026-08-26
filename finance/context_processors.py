def notifications(request):
    if not request.user.is_authenticated:
        return {}
    notification_qs = request.user.notifications.filter(is_read=False)
    return {
        'unread_notifications': notification_qs[:5],
        'unread_notification_count': notification_qs.count(),
    }
