import hashlib
import hmac

from aiohttp import web

from ..config import settings
from ..repo import add_payment


def expected_sig(user_id: int, message_id: int) -> str:
    return hmac.new(
        settings.token_secret.encode(),
        f"{user_id}:{message_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


async def paid_handler(request: web.Request) -> web.Response:
    data = await request.json()
    uid, mid = int(data["user_id"]), int(data["message_id"])
    if not hmac.compare_digest(data.get("sig", ""), expected_sig(uid, mid)):
        return web.json_response({"ok": False}, status=403)
    await add_payment(uid, mid, int(data.get("amount_kop", 100)))
    return web.json_response({"ok": True})


async def start_webhook() -> web.AppRunner:
    app = web.Application()
    app.router.add_post("/api/paid", paid_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", settings.webhook_port).start()
    return runner