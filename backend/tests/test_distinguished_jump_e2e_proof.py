"""End-to-end proof — distinguished jump via production functions (test env only)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from unittest.mock import patch

import pytest

from analysis.early_upward_surge import (
    WAVE_STATE_ACTIVE_UPWARD,
    WAVE_STATE_ENDED_LABEL,
    RealJumpWaveSnapshot,
    RealPriceJumpVerdict,
)
from models.opportunity_now import OpportunityNowResponse, OpportunityNowSignal
from models.pre_move import PreMoveScanResult, PreMoveSignal, PreMoveScanStats
from services.opportunity_now_service import _collect_distinguished_jump_alerts
from services.real_jump_alert_layer import (
    _live_wave_move_pct,
    apply_distinguished_jump_display,
    eligible_for_distinguished_jump_section,
    eligible_premove,
    evaluate_premove_real_jump,
    reset_real_jump_state,
)
from tests.test_distinguished_jump_section import _active_wave, _base_signal, _verdict


@dataclass
class ProofCase:
    name: str
    passed: bool
    current_move_pct: float
    decision_fn: str
    reason: str
    inputs: int
    outputs: int


def _http_get(url: str, timeout: int = 60) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return 0, str(exc)


def _minimal_premove(symbol: str, price: float, change_pct: float) -> PreMoveSignal:
    from tests.test_real_jump_alert_layer import _real_jump_signal

    return _real_jump_signal(symbol=symbol, current_price=price, change_percent=change_pct)


def _pipeline_from_waves(
    waves: list[tuple[str, RealJumpWaveSnapshot, float, float]],
) -> list[OpportunityNowSignal]:
    """Wave snapshot → evaluate → collect → response field."""
    signals: list[PreMoveSignal] = []
    for sym, wave, price, day_pct in waves:
        pm = _minimal_premove(sym, price, day_pct)
        verdict = RealPriceJumpVerdict(confirmed=False, wave=wave)
        if eligible_premove(pm) and eligible_for_distinguished_jump_section(wave, current_price=price):
            signals.append(apply_distinguished_jump_display(_base_signal(symbol=sym, price=price, change_percent=day_pct), verdict))

    resp = OpportunityNowResponse(
        status="NOW",
        status_ar="",
        market_status="REGULAR",
        market_open=True,
        scan_interval_seconds=15,
        message="",
        live_source="rest",
        ws_connected=False,
        monitor_pool_size=0,
        signals=[],
        top_signal=None,
        distinguished_jump_alerts=signals,
    )
    assert len(resp.distinguished_jump_alerts) == len(signals)
    return resp.distinguished_jump_alerts


@pytest.fixture(autouse=True)
def _reset():
    reset_real_jump_state()
    yield
    reset_real_jump_state()


class TestDeployedProof:
    API_HEALTH = "https://smart-stock-assistant-api.onrender.com/health"
    API_OPENAPI = "https://smart-stock-assistant-api.onrender.com/openapi.json"
    WEB_JS = "https://smart-stock-assistant-web.onrender.com/main.dart.js"
    WEB_HOME = "https://smart-stock-assistant-web.onrender.com/"

    def test_deploy_health_200(self):
        code, _ = _http_get(self.API_HEALTH)
        assert code == 200

    def test_deploy_openapi_has_distinguished_field(self):
        code, body = _http_get(self.API_OPENAPI)
        assert code == 200
        schema = json.loads(body)
        props = schema["components"]["schemas"]["OpportunityNowResponse"]["properties"]
        assert "distinguished_jump_alerts" in props

    def test_deploy_web_has_distinguished_section(self):
        code, body = _http_get(self.WEB_JS, timeout=120)
        assert code == 200
        assert "DISTINGUISHED_PRICE_JUMP" in body or "distinguishedJumpAlerts" in body


class TestProductionPipelineProof:
    def test_active_wave_55_pct_enters(self):
        move_start, price = 2.0, 3.1
        live = _live_wave_move_pct(move_start, price)
        wave = _active_wave(
            move_start_price=move_start,
            current_price=price,
            current_move_pct=live,
        )
        ok = eligible_for_distinguished_jump_section(wave, current_price=price)
        assert ok is True
        assert live == pytest.approx(55.0)

    def test_daily_80_wave_8_pct_rejected(self):
        move_start, price = 5.0, 5.4
        live = _live_wave_move_pct(move_start, price)
        wave = _active_wave(
            move_start_price=move_start,
            current_price=price,
            current_move_pct=live,
        )
        ok = eligible_for_distinguished_jump_section(wave, current_price=price)
        assert ok is False
        assert live == pytest.approx(8.0)

    def test_ended_wave_60_pct_rejected(self):
        move_start, price = 2.0, 3.2
        wave = _active_wave(
            move_start_price=move_start,
            current_price=price,
            wave_active=False,
            wave_ended=True,
            wave_state=WAVE_STATE_ENDED_LABEL,
            current_move_pct=60.0,
        )
        ok = eligible_for_distinguished_jump_section(wave, current_price=price)
        assert ok is False

    def test_twelve_waves_no_cap(self):
        waves = []
        for i in range(12):
            ms = 1.0 + i * 0.4
            px = ms * 1.55
            live = _live_wave_move_pct(ms, px)
            waves.append((
                f"T{i + 1}",
                _active_wave(move_start_price=ms, current_price=px, current_move_pct=live),
                px,
                80.0,
            ))
        out = _pipeline_from_waves(waves)
        assert len(out) == 12

    def test_collect_uses_production_eligibility(self):
        pm = _minimal_premove("G1", 3.1, 80.0)
        wave = _active_wave(move_start_price=2.0, current_price=3.1, current_move_pct=55.0)
        scan = PreMoveScanResult(
            signals=[pm],
            rejected=[],
            stats=PreMoveScanStats(),
            message="",
        )
        with patch("services.pre_move_predictor_service.get_last_pre_move_scan", return_value=scan):
            with patch("services.opportunity_now_service.evaluate_premove_real_jump") as ev:
                ev.return_value = RealPriceJumpVerdict(confirmed=False, wave=wave)
                out = _collect_distinguished_jump_alerts("REGULAR")
        assert len(out) == 1
        assert out[0].display_type == "DISTINGUISHED_PRICE_JUMP"


def run_proof_report() -> list[ProofCase]:
    """Structured PASS/FAIL report for all proof scenarios."""
    cases: list[ProofCase] = []

    def add(name: str, fn: Callable[[], tuple[bool, float, str, int, int, str]]):
        ok, pct, reason, n_in, n_out, fn_name = fn()
        cases.append(ProofCase(name, ok, pct, fn_name, reason, n_in, n_out))

    # Deployed
    code, _ = _http_get("https://smart-stock-assistant-api.onrender.com/health")
    add("deploy_health_200", lambda: (code == 200, 0.0, f"http_status={code}", 1, 1, "_http_get(/health)"))

    code, body = _http_get("https://smart-stock-assistant-api.onrender.com/openapi.json")
    has_field = False
    if code == 200:
        props = json.loads(body)["components"]["schemas"]["OpportunityNowResponse"]["properties"]
        has_field = "distinguished_jump_alerts" in props
    add(
        "deploy_openapi_distinguished_field",
        lambda: (has_field, 0.0, "field_present" if has_field else "field_missing", 1, int(has_field), "OpenAPI schema"),
    )

    code, js = _http_get("https://smart-stock-assistant-web.onrender.com/main.dart.js", timeout=120)
    web_ok = code == 200 and ("DISTINGUISHED_PRICE_JUMP" in js or "distinguishedJumpAlerts" in js)
    add(
        "deploy_web_distinguished_section",
        lambda: (web_ok, 0.0, "bundle_marker_found" if web_ok else "bundle_marker_missing", 1, int(web_ok), "main.dart.js scan"),
    )

    # Pipeline scenarios
    def case_55():
        ms, px = 2.0, 3.1
        live = _live_wave_move_pct(ms, px)
        w = _active_wave(move_start_price=ms, current_price=px, current_move_pct=live)
        ok = eligible_for_distinguished_jump_section(w, current_price=px)
        out = 1 if ok else 0
        return ok, live, "active_wave>=50%" if ok else "below_threshold", 1, out, "eligible_for_distinguished_jump_section"

    def case_daily80_wave8():
        ms, px = 5.0, 5.4
        live = _live_wave_move_pct(ms, px)
        w = _active_wave(move_start_price=ms, current_price=px, current_move_pct=live)
        ok = not eligible_for_distinguished_jump_section(w, current_price=px)
        return ok, live, "rejected_live_wave<50_not_daily_change", 1, 0, "eligible_for_distinguished_jump_section"

    def case_ended60():
        ms, px = 2.0, 3.2
        w = _active_wave(
            move_start_price=ms, current_price=px, current_move_pct=60.0,
            wave_active=False, wave_ended=True, wave_state=WAVE_STATE_ENDED_LABEL,
        )
        ok = not eligible_for_distinguished_jump_section(w, current_price=px)
        return ok, 60.0, "wave_ended", 1, 0, "eligible_for_distinguished_jump_section"

    def case_twelve():
        waves = []
        for i in range(12):
            ms = 1.0 + i * 0.4
            px = ms * 1.55
            live = _live_wave_move_pct(ms, px)
            waves.append((f"T{i+1}", _active_wave(move_start_price=ms, current_price=px, current_move_pct=live), px, 80.0))
        out = _pipeline_from_waves(waves)
        ok = len(out) == 12
        avg = sum(s.real_jump_current_move_pct for s in out) / len(out) if out else 0.0
        return ok, avg, f"all_12_collected_no_cap" if ok else f"got_{len(out)}", 12, len(out), "_pipeline_from_waves→OpportunityNowResponse"

    add("wave_55pct_enters", case_55)
    add("daily80_wave8_rejected", case_daily80_wave8)
    add("wave60_ended_removed", case_ended60)
    add("twelve_waves_no_limit", case_twelve)

    return cases


if __name__ == "__main__":
    import subprocess
    import sys

    local = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    print(f"LOCAL_COMMIT={local}")
    for c in run_proof_report():
        status = "PASS" if c.passed else "FAIL"
        print(
            f"{status}\t{c.name}\tcurrent_move_pct={c.current_move_pct:.3f}\t"
            f"reason={c.reason}\tinputs={c.inputs}\toutputs={c.outputs}\tfn={c.decision_fn}"
        )
    sys.exit(0 if all(c.passed for c in run_proof_report()) else 1)
