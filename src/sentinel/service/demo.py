"""A demo server on the simulated feed of development seed 11: the world's articles and its simulated model.

Only this file connects the service to the simulation. The API itself sees master data, a reader and a store.
"""

from __future__ import annotations

from fastapi import FastAPI

from .. import config
from ..world.luck import draw_luck
from ..world.reader_sim import SimReader
from ..world.world import World
from .api import create_app
from .store import Store


def create_demo_app(seed: int = 11, days: int = 3) -> FastAPI:
    world = World(seed, "dev")
    reader = SimReader(world, draw_luck(world), "model_a")
    app = create_app(world.master_data(), config.platform(), reader, "model_a", Store())
    from fastapi.testclient import TestClient

    client = TestClient(app)
    for m in world.messages():
        if m.published_h < days * 24:
            client.post("/v1/signals", json={"msg_id": m.msg_id, "source": m.source, "published_h": m.published_h, "headline": m.headline, "body": m.body})
    return app
