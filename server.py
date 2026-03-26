# Fix the imports at the top of server.py - replace the problematic line with:

from telethon.tl.types import (
    MessageEntityMention, 
    MessageEntityTextUrl, 
    TypeMessageEntity, 
    DocumentAttributeSticker
)
# DocumentAttributeEmoji doesn't exist in Telethon - remove it

# Also add these necessary imports:
from telethon.tl.types import (
    InputPeerUser,
    InputPeerChat,
    InputPeerChannel,
    MessageMediaPhoto,
    MessageMediaDocument,
    MessageMediaVideo,
    MessageMediaAudio,
    DocumentAttributeFilename,
    DocumentAttributeAudio,
    DocumentAttributeVideo,
    MessageEntityUrl,
    MessageEntityEmail,
    MessageEntityPhone,
    MessageEntityHashtag,
    MessageEntityCashtag,
    MessageEntityBotCommand,
    MessageEntityMentionName,
    MessageEntityTextUrl,
    MessageEntityPre,
    MessageEntityCode,
    MessageEntityItalic,
    MessageEntityBold,
    MessageEntityUnderline,
    MessageEntityStrike,
    MessageEntityBlockquote,
    MessageEntitySpoiler,
    MessageEntityCustomEmoji
)
