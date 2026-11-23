"""Every design meets the same world and the same draws; a rerun gives the same numbers."""

from __future__ import annotations

from sentinel import config
from sentinel.platform.prompt import build_prompt
from sentinel.sim.evaluate import seed_metrics
from sentinel.sim.simulate import SeedSim
from sentinel.world.luck import draw_luck
from sentinel.world.reader_sim import SimReader
from sentinel.world.world import World


def test_the_world_and_its_luck_are_fixed_by_the_seed() -> None:
    a, b = World(5, "dev"), World(5, "dev")
    assert [m.text for m in a.messages()] == [m.text for m in b.messages()]
    assert a.impacts == b.impacts
    assert draw_luck(a).reader == draw_luck(b).reader


def test_the_simulated_model_reads_a_message_the_same_way_for_every_design() -> None:
    w = World(5, "dev")
    luck = draw_luck(w)
    r1, r2 = SimReader(w, luck, "model_a"), SimReader(w, luck, "model_a")
    msgs = w.messages()[:60]
    first = [r1.read(build_prompt(m)).text for m in msgs]
    second = [r2.read(build_prompt(m)).text for m in reversed(msgs)][::-1]
    assert first == second


def test_people_decide_the_same_thing_whichever_design_asks() -> None:
    w = World(5, "dev")
    luck = draw_luck(w)
    assert luck.person("manager", "E0001", "steel_coil") == draw_luck(w).person("manager", "E0001", "steel_coil")


def test_a_rerun_gives_identical_metrics() -> None:
    d = config.designs()["designs"]
    a = SeedSim(5, "dev")
    b = SeedSim(5, "dev")
    for name in ("status_quo", "platform"):
        ma = seed_metrics(a.world, a.run(name, d[name], config.platform()))
        mb = seed_metrics(b.world, b.run(name, d[name], config.platform()))
        assert ma == mb


def test_the_heldout_world_differs_on_purpose() -> None:
    dev, held = World(5, "dev"), World(5, "heldout")
    assert held.cfg["injection_p"] > dev.cfg["injection_p"]
    assert "tariff_wave" in held.cfg and "tariff_wave" not in dev.cfg
