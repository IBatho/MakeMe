# Import provider modules so their @register decorators run at startup.
from app.integrations.notion.provider import NotionProvider  # noqa: F401
from app.integrations.google_calendar.provider import GoogleCalendarProvider  # noqa: F401
from app.integrations.apple_caldav.provider import AppleCalDAVProvider  # noqa: F401
from app.integrations.microsoft_365.provider import Microsoft365Provider  # noqa: F401
