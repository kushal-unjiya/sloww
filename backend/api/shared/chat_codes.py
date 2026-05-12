"""Integer codes for chat messages (roles and completion status)."""

from api.shared.status_codes import STATUS_PROCESSED

# message.role
CHAT_ROLE_USER = 1
CHAT_ROLE_ASSISTANT = 2

# message.status — use same processed code when turn is complete
MESSAGE_STATUS_COMPLETE = STATUS_PROCESSED
