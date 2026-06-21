"""Защита от SSRF: валидация исходящих URL (https + блок внутренних адресов)."""
import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

from ...core.errors import ValidationError


def _is_blocked_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False  # не IP-литерал — проверится резолвом
    return (ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def _resolve_and_check(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        raise ValidationError(f"Не удалось разрешить хост: {host}")
    for info in infos:
        addr = info[4][0]
        if _is_blocked_ip(addr):
            raise ValidationError("URL указывает на внутренний/приватный адрес — запрещено")


async def validate_outbound_url(
    url: str,
    *,
    allowed_domains: tuple[str, ...] | None = None,
    allow_http: bool = False,
) -> None:
    """Бросает ValidationError, если URL небезопасен для исходящего запроса.

    - схема только https (или http при allow_http);
    - хост обязателен; IP-литералы из внутренних диапазонов запрещены;
    - при allowed_domains — хост обязан совпадать/заканчиваться на один из доменов;
    - резолв хоста и блок, если ЛЮБОЙ адрес внутренний (DNS-rebinding защита).
    """
    p = urlparse(url or "")
    allowed_schemes = ("https", "http") if allow_http else ("https",)
    if p.scheme not in allowed_schemes:
        raise ValidationError("Разрешён только https URL")
    host = (p.hostname or "").lower()
    if not host:
        raise ValidationError("URL без хоста")
    if _is_blocked_ip(host):
        raise ValidationError("URL указывает на внутренний/приватный адрес — запрещено")
    if allowed_domains is not None and not any(
        host == d or host.endswith("." + d) for d in allowed_domains
    ):
        raise ValidationError(f"Хост не в списке разрешённых: {host}")
    await asyncio.to_thread(_resolve_and_check, host)
