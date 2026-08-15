"""Интеграция ATS Talantix (talantix.ru): импорт кандидатов + история комментариев.

Зеркалит механику импорта из «Поток» (services/integrations/potok), но источник —
GraphQL API Talantix. Главная ценность — импорт истории комментариев кандидата
(CommentAdded / HhCommentAdded) с сохранением автора и даты оригинала.
"""
