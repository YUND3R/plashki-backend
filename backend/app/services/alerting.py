from app.notifications.application import NotificationFacade as AlertService
from app.notifications.providers import get_notification_facade

alert_service = get_notification_facade()