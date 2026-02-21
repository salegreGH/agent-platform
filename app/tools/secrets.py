import keyring
SERVICE = "agent_platform_v4"
def set_secret(name: str, value: str) -> None:
    if not value:
        raise ValueError("Secret buit")
    keyring.set_password(SERVICE, name, value)
def get_secret(name: str) -> str | None:
    try:
        return keyring.get_password(SERVICE, name)
    except Exception:
        return None
