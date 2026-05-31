from zenlabs_sdk import ZenClient

from service.config import settings


def get_client() -> ZenClient:
    token = (settings.zenlabs_token or "").strip()
    if not token:
        raise RuntimeError("ZENLABS_TOKEN is not set in environment")
    return ZenClient(
        token=token,
        base_url=settings.zenlabs_base_url,
        tenant_id=settings.tenant_id,
    )
