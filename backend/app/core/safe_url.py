import ipaddress
from urllib.parse import urlparse


def allowed_host_from_url(value: str) -> str:
    host = (urlparse(value.strip()).hostname or "").lower()
    if not host:
        raise ValueError("URL провайдера не содержит host.")
    return host


def validate_outbound_https_url(value: str, *, allowed_hosts: frozenset[str]) -> str:
    if len(value) > 2048:
        raise ValueError("URL результата слишком длинный.")
    parsed = urlparse(value.strip())
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("Разрешены только HTTPS URL результата без credentials.")
    host = parsed.hostname.lower()
    if host not in allowed_hosts:
        raise ValueError("Host результата не разрешён.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP-адреса в URL результата запрещены.")
    return value.strip()
