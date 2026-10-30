import hashlib
import hmac

import pytest

from app.core.config import settings
from app.services import command_signing, mqtt_service as m


class Info:
    rc = 0
    def wait_for_publish(self, timeout=None): pass
    def is_published(self): return True


class Fake:
    def __init__(self): self.calls = []
    def is_connected(self): return True
    def publish(self, topic, payload=None, qos=0, retain=False):
        self.calls.append((topic, payload, qos, retain)); return Info()


@pytest.fixture()
def fake(monkeypatch, env):
    f = Fake()
    monkeypatch.setattr(m, "_client", f)
    monkeypatch.setattr(settings, "mqtt_enabled", True)
    return f


def test_unsigned_by_default(fake):
    m.publish_water("plant01", 5)
    assert fake.calls[0][1] == "ON:5"


def test_signed_format_counter_and_mac(fake, monkeypatch):
    monkeypatch.setattr(settings, "command_signing_key", "k" * 32)
    m.publish_water("plant01", 7); m.publish_water("plant01", 7)
    (_, p1, *_), (_, p2, *_) = fake.calls
    ON, s, c1, mac1 = p1.split(":")
    assert ON == "ON" and s == "7" and len(mac1) == 16 and int(p2.split(":")[2]) > int(c1)  # strictly increasing
    assert mac1 == hmac.new(b"k" * 32, f"plant01|7|{c1}".encode(), hashlib.sha256).hexdigest()[:16]
    assert command_signing.mac("plant02", 7, int(c1)) != mac1  # bound to the plant id


def test_counter_never_goes_backwards_after_db_reset(env, monkeypatch):
    monkeypatch.setattr(settings, "command_signing_key", "k" * 32)
    import time
    c = command_signing.next_counter("plant01")
    assert c >= int(time.time()) - 1
    from app.db.database import db_session
    with db_session() as db:
        db.execute("DELETE FROM command_counters")
    assert command_signing.next_counter("plant01") >= c  # unix-time floor protects against reuse
