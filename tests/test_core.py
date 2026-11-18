import asyncio

from copilot.bus import Bus
from copilot.config import load
from copilot.obs.latency import LatencyBook


def test_bus_topics_wildcards_and_drop_oldest():
    async def run():
        bus = Bus()
        exact, wild, everything = bus.subscribe("asr.final"), bus.subscribe("asr.*"), bus.subscribe("*")
        small = bus.subscribe("nlu.result", maxsize=2)
        assert bus.publish("asr.final", 1) == 3
        assert bus.publish("asr.partial", 2) == 2
        for i in range(5):
            bus.publish("nlu.result", i)
        assert await exact.get() == ("asr.final", 1)
        assert [await wild.get(), await wild.get()] == [("asr.final", 1), ("asr.partial", 2)]
        assert everything.queue.qsize() == 7
        assert small.dropped == 3 and (await small.get())[1] == 3
        exact.close()
        assert bus.publish("asr.final", 9) == 2
    asyncio.run(run())


def test_config_layers(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "default.yaml").write_text("server: {port: 1, host: a}\nasr: {engine: x}\n")
    (tmp_path / "config" / "local.yaml").write_text("server: {port: 2}\n")
    cfg = load(env={"COPILOT_ASR__ENGINE": "y", "COPILOT_GRAPHICS__AUTO_PROGRAM": "true", "OTHER": "z"}, root=tmp_path)
    assert cfg == {"server": {"port": 2, "host": "a"}, "asr": {"engine": "y"}, "graphics": {"auto_program": True}}


def test_default_config_loads():
    cfg = load(env={})
    assert cfg["season"] == "2024-25" and cfg["server"]["port"] == 8765


def test_latency_book_stages():
    lb = LatencyBook()
    for i in range(100):
        lb.add_trace({"audio_end": 0, "asr_emit": 300 + i, "nlu_out": 310 + i, "select_out": 312 + i,
                      "ws_send": 313 + i, "t_paint": 330 + i})
    s = lb.summary()
    assert s["nlu"]["p50"] == 10 and s["total"]["p95"] == 424 and s["asr"]["n"] == 100
    lb.add_trace({"audio_end": 0})
    assert lb.summary()["total"]["n"] == 100
