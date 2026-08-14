"""Closed-loop FSO campaign: geometry × PAT × channel × modem."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np

from aurora_qsd.core.constants import DEFAULT_RHO
from aurora_qsd.core.iss import iss_bound
from aurora_qsd.optical.channel import (
    TerminalSpec,
    link_budget,
    lognormal_fades,
)
from aurora_qsd.optical.constants import (
    AVAILABILITY_NONINFERIOR_PP,
    DEFAULT_JITTER_CORR_S,
    DEFAULT_JITTER_RMS_URAD,
    DEFAULT_PAT_DT,
    ISS_COVERAGE_TARGET,
    MIN_ELEVATION_DEG,
    SNR_OUTAGE_DB,
)
from aurora_qsd.optical.modem import Modulation, bit_error_rate
from aurora_qsd.optical.orbits import sample_geometry
from aurora_qsd.optical.pat import (
    ControllerName,
    PATPlant,
    PIDController,
    QSDISSController,
    colored_jitter,
    pat_aurora_condition,
)


class ScenarioName(str, Enum):
    ISL = "isl"
    DOWNLINK = "downlink"
    STRESS = "stress"


@dataclass
class ControllerRun:
    name: str
    t: np.ndarray
    err_urad: np.ndarray
    snr_db: np.ndarray
    p_rx_w: np.ndarray
    ber: np.ndarray
    iss_bound_urad: np.ndarray
    mean_err_urad: float
    rms_err_urad: float
    availability: float
    mean_ber: float
    mean_snr_db: float
    iss_coverage: float
    acquisition_samples: int


@dataclass
class SimulationResult:
    scenario: str
    spec: TerminalSpec
    aurora: dict
    runs: dict[str, ControllerRun]
    verdicts: dict[str, dict]
    notes: str = ""

    def summary_rows(self) -> list[dict]:
        rows = []
        for run in self.runs.values():
            rows.append(
                {
                    "scenario": self.scenario,
                    "controller": run.name,
                    "mean_err_urad": run.mean_err_urad,
                    "rms_err_urad": run.rms_err_urad,
                    "availability": run.availability,
                    "mean_ber": run.mean_ber,
                    "mean_snr_db": run.mean_snr_db,
                    "iss_coverage": run.iss_coverage,
                    "iss_bound_urad": float(run.iss_bound_urad[-1]) if len(run.iss_bound_urad) else 0.0,
                    "acquisition_samples": run.acquisition_samples,
                }
            )
        return rows


def _make_controller(name: ControllerName, dt: float):
    if name is ControllerName.OPEN:
        return None
    if name is ControllerName.PID:
        return PIDController(dt=dt)
    if name is ControllerName.QSD:
        return QSDISSController(dt=dt, wrong_well=False)
    if name is ControllerName.QSD_WRONG:
        return QSDISSController(dt=dt, wrong_well=True)
    raise ValueError(name)


def _geometry_series(
    scenario: ScenarioName,
    t: np.ndarray,
    spec: TerminalSpec,
    arg_lat0_deg: float,
):
    kind = "isl" if scenario is ScenarioName.ISL else "downlink"
    # Stress uses ISL geometry with harsher jitter (handled by the caller)
    if scenario is ScenarioName.STRESS:
        kind = "isl"
    return sample_geometry(
        kind,
        t,
        spec.wavelength_m,
        altitude_km=550.0,
        anomaly_offset_deg=20.0,
        arg_lat0_deg=arg_lat0_deg,
    )


def _run_controller(
    name: ControllerName,
    t: np.ndarray,
    geo_list,
    spec: TerminalSpec,
    disturbance: np.ndarray,
    fades: np.ndarray,
    include_atmosphere: bool,
    e0_urad: float,
    d_bound_rad: float,
    rho: float,
    rng: np.random.Generator,
    sensor_noise_rad: float = 0.4e-6,
) -> ControllerRun:
    dt = float(t[1] - t[0]) if len(t) > 1 else DEFAULT_PAT_DT
    plant = PATPlant(dt=dt)
    plant.reset()
    ctrl = _make_controller(name, dt)
    if ctrl is not None:
        ctrl.reset()

    n = len(t)
    err = np.zeros((n, 2))
    snr_db = np.zeros(n)
    p_rx = np.zeros(n)
    ber = np.zeros(n)
    fsm = np.zeros(2)

    for i in range(n):
        e_true = disturbance[i] - fsm
        e_meas = e_true + rng.normal(0.0, sensor_noise_rad, size=2)
        if ctrl is None:
            u = np.zeros(2)
        else:
            u = ctrl.update(e_meas)
        fsm = plant.step(float(u[0]), float(u[1]))
        e_true = disturbance[i] - fsm
        err[i] = e_true
        theta_err = float(np.linalg.norm(e_true))
        geo = geo_list[i]
        fade = float(fades[i])
        budget = link_budget(
            geo,
            spec,
            theta_err_rad=theta_err,
            fade_linear=fade,
            include_atmosphere=include_atmosphere,
        )
        if include_atmosphere and geo.elevation_deg < MIN_ELEVATION_DEG:
            budget_snr = -80.0
            budget_p = 0.0
            snr_linear = 0.0
        else:
            budget_snr = budget.snr_db
            budget_p = budget.p_rx_w
            snr_linear = budget.snr_elec
        snr_db[i] = budget_snr
        p_rx[i] = budget_p
        ber[i] = bit_error_rate(snr_linear, Modulation.OOK)

    radial = np.linalg.norm(err, axis=1)
    # ISS envelope in radians, converted to μrad for the plot
    e0 = e0_urad * 1e-6
    bound = np.array([iss_bound(e0, i, rho, d_bound_rad) for i in range(n)])
    coverage = float(np.mean(radial <= bound + 1e-12))

    available = snr_db >= SNR_OUTAGE_DB
    # Acquisition: first time radial error stays under 4 μrad for 20 samples
    acq = n
    thresh = 12e-6
    hold = 20
    below = radial < thresh
    for i in range(n - hold):
        if np.all(below[i : i + hold]):
            acq = i
            break

    return ControllerRun(
        name=name.value,
        t=t,
        err_urad=radial * 1e6,
        snr_db=snr_db,
        p_rx_w=p_rx,
        ber=ber,
        iss_bound_urad=bound * 1e6,
        mean_err_urad=float(np.mean(radial) * 1e6),
        rms_err_urad=float(np.sqrt(np.mean(radial**2)) * 1e6),
        availability=float(np.mean(available)),
        mean_ber=float(np.mean(ber)),
        mean_snr_db=float(np.mean(snr_db[np.isfinite(snr_db)])),
        iss_coverage=coverage,
        acquisition_samples=int(acq),
    )


def _verdicts(runs: dict[str, ControllerRun]) -> dict[str, dict]:
    """Pre-registered tests. NULL is a valid, publishable outcome."""
    open_r = runs[ControllerName.OPEN.value]
    pid_r = runs[ControllerName.PID.value]
    qsd_r = runs[ControllerName.QSD.value]
    wrong_r = runs[ControllerName.QSD_WRONG.value]

    t1_pass = qsd_r.mean_err_urad < open_r.mean_err_urad
    terminal_bound = float(qsd_r.iss_bound_urad[-1]) if len(qsd_r.iss_bound_urad) else 0.0
    vacuous_iss = terminal_bound > 2.0 * max(open_r.rms_err_urad, 1e-9)
    t2_pass = qsd_r.iss_coverage >= ISS_COVERAGE_TARGET and not vacuous_iss
    delta_pp = (qsd_r.availability - pid_r.availability) * 100.0
    t3_pass = delta_pp >= -AVAILABILITY_NONINFERIOR_PP
    n_samples = len(qsd_r.t)
    neither_acq = (
        qsd_r.acquisition_samples >= n_samples and pid_r.acquisition_samples >= n_samples
    )
    t4_pass = (not neither_acq) and (qsd_r.acquisition_samples <= pid_r.acquisition_samples)
    t5_pass = qsd_r.mean_err_urad < wrong_r.mean_err_urad

    def pack(name, passed, detail):
        return {
            "test": name,
            "passed": bool(passed),
            "verdict": "PASS" if passed else "NULL",
            "detail": detail,
        }

    return {
        "T1_qsd_beats_openloop": pack(
            "T1",
            t1_pass,
            f"QSD mean {qsd_r.mean_err_urad:.3f} μrad vs open {open_r.mean_err_urad:.3f} μrad",
        ),
        "T2_iss_coverage": pack(
            "T2",
            t2_pass,
            (
                f"ISS coverage {qsd_r.iss_coverage:.3f} (target {ISS_COVERAGE_TARGET}); "
                f"terminal bound {terminal_bound:.2f} μrad"
                + (" [VACUOUS vs 2× open RMS]" if vacuous_iss else "")
            ),
        ),
        "T3_availability_noninferior_to_pid": pack(
            "T3",
            t3_pass,
            f"QSD availability {qsd_r.availability:.3f} vs PID {pid_r.availability:.3f} "
            f"(Δ={delta_pp:+.2f} pp, floor −{AVAILABILITY_NONINFERIOR_PP} pp)",
        ),
        "T4_acquisition_vs_pid": pack(
            "T4",
            t4_pass,
            (
                "neither controller acquired (no 20-sample hold under 12 μrad)"
                if neither_acq
                else f"QSD acq {qsd_r.acquisition_samples} samples vs PID {pid_r.acquisition_samples}"
            ),
        ),
        "T5_wrong_well_is_worse": pack(
            "T5",
            t5_pass,
            f"QSD mean {qsd_r.mean_err_urad:.3f} vs wrong-well {wrong_r.mean_err_urad:.3f} μrad",
        ),
    }


def run_scenario(
    scenario: ScenarioName = ScenarioName.ISL,
    duration_s: float = 4.0,
    dt: float = DEFAULT_PAT_DT,
    seed: int = 0,
    jitter_rms_urad: float | None = None,
    acq_offset_urad: float = 50.0,
    arg_lat0_deg: float = 0.0,
) -> SimulationResult:
    """Run four controllers on one scenario. Deterministic for a given seed."""
    rng = np.random.default_rng(seed)
    n = int(max(8, round(duration_s / dt)))
    t = np.arange(n) * dt

    if scenario is ScenarioName.DOWNLINK:
        spec = TerminalSpec(
            name="leo-ogs",
            rx_aperture_m=0.40,
            bit_rate_hz=10e9,
        )
        include_atmosphere = True
        arg = arg_lat0_deg
        rms = DEFAULT_JITTER_RMS_URAD if jitter_rms_urad is None else jitter_rms_urad
    elif scenario is ScenarioName.STRESS:
        spec = TerminalSpec(name="leo-isl-stress")
        include_atmosphere = False
        arg = arg_lat0_deg
        rms = 40.0 if jitter_rms_urad is None else jitter_rms_urad
    else:
        spec = TerminalSpec(name="leo-isl")
        include_atmosphere = False
        arg = arg_lat0_deg
        rms = DEFAULT_JITTER_RMS_URAD if jitter_rms_urad is None else jitter_rms_urad

    geo_list = _geometry_series(scenario, t, spec, arg_lat0_deg=arg)
    rms_rad = rms * 1e-6
    disturbance = colored_jitter(
        n, dt, rms_rad, DEFAULT_JITTER_CORR_S, rng, n_axes=2
    )
    # Acquisition transient: start 50 μrad off boresight on az
    disturbance = disturbance + np.array([acq_offset_urad * 1e-6, 0.0]) * np.exp(
        -t / 0.15
    )[:, None]

    if include_atmosphere:
        # Use mid-pass scintillation index as a constant σ_I² for the fade process
        from aurora_qsd.optical.channel import downlink_scintillation_index

        mid = geo_list[n // 2]
        sig_i = downlink_scintillation_index(
            spec.wavelength_m,
            max(mid.elevation_deg, MIN_ELEVATION_DEG),
            spec.rx_aperture_m,
            h_sat_m=550e3,
            h_gs_m=3055.0,
        )
        corr = max(1, int(0.004 / dt))  # ~4 ms Greenwood-class
        fades = lognormal_fades(n, sig_i, corr, rng)
    else:
        fades = np.ones(n)

    d_bound = float(np.percentile(np.linalg.norm(np.diff(disturbance, axis=0), axis=1), 95))
    e0 = acq_offset_urad
    rho = DEFAULT_RHO

    runs = {}
    for name in (
        ControllerName.OPEN,
        ControllerName.PID,
        ControllerName.QSD,
        ControllerName.QSD_WRONG,
    ):
        runs[name.value] = _run_controller(
            name,
            t,
            geo_list,
            spec,
            disturbance,
            fades,
            include_atmosphere,
            e0_urad=e0,
            d_bound_rad=d_bound,
            rho=rho,
            rng=np.random.default_rng(seed + 17),
        )

    aurora = pat_aurora_condition(rho, dt, DEFAULT_JITTER_CORR_S)
    verdicts = _verdicts(runs)
    n_pass = sum(1 for v in verdicts.values() if v["passed"])
    notes = (
        f"{scenario.value}: {n_pass}/5 pre-registered tests PASS. "
        "Simulation only — not a hardware result. "
        "θ* is a control-Lyapunov coordinate, not a beam pointing offset."
    )
    return SimulationResult(
        scenario=scenario.value,
        spec=spec,
        aurora=aurora,
        runs=runs,
        verdicts=verdicts,
        notes=notes,
    )


def run_campaign(
    duration_s: float = 4.0,
    dt: float = DEFAULT_PAT_DT,
    seed: int = 0,
    out_dir: Path | None = None,
) -> dict[str, SimulationResult]:
    """ISL + downlink + stress. Optionally write CSV/PNG under ``out_dir``."""
    results = {}
    for sc in (ScenarioName.ISL, ScenarioName.DOWNLINK, ScenarioName.STRESS):
        results[sc.value] = run_scenario(sc, duration_s=duration_s, dt=dt, seed=seed)
    if out_dir is not None:
        write_campaign(results, Path(out_dir))
    return results


def write_campaign(results: dict[str, SimulationResult], out_dir: Path) -> None:
    """Write summary CSVs, timeseries, and figures."""
    import csv

    out_dir = Path(out_dir)
    fig_dir = out_dir / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    verdict_rows = []
    for res in results.values():
        rows.extend(res.summary_rows())
        for v in res.verdicts.values():
            verdict_rows.append({"scenario": res.scenario, **v})
        q = res.runs["qsd"]
        p = res.runs["pid"]
        o = res.runs["open"]
        ts_path = out_dir / f"timeseries_{res.scenario}.csv"
        with ts_path.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "t_s",
                    "qsd_err_urad",
                    "pid_err_urad",
                    "open_err_urad",
                    "qsd_iss_bound_urad",
                    "qsd_snr_db",
                    "pid_snr_db",
                    "qsd_ber",
                ]
            )
            for i in range(len(q.t)):
                w.writerow(
                    [
                        q.t[i],
                        q.err_urad[i],
                        p.err_urad[i],
                        o.err_urad[i],
                        q.iss_bound_urad[i],
                        q.snr_db[i],
                        p.snr_db[i],
                        q.ber[i],
                    ]
                )

    def _write_dicts(path: Path, data: list[dict]) -> None:
        if not data:
            path.write_text("")
            return
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            w.writeheader()
            w.writerows(data)

    _write_dicts(out_dir / "optical_link_summary.csv", rows)
    _write_dicts(out_dir / "optical_link_verdicts.csv", verdict_rows)

    try:
        _write_figures(results, fig_dir)
    except ImportError:
        print("matplotlib not installed; skipping figures")


def _write_figures(results: dict[str, SimulationResult], fig_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from aurora_qsd.core.constants import THETA_STAR
    from aurora_qsd.core.phase_potential import phase_potential

    # Pointing residual, one panel per scenario
    n_sc = len(results)
    fig, axes = plt.subplots(n_sc, 1, figsize=(9.5, 3.2 * n_sc), sharex=False)
    if n_sc == 1:
        axes = [axes]
    colors = {"open": "#888888", "pid": "#1f77b4", "qsd": "#d62728", "qsd_wrong": "#ff7f0e"}
    for ax, res in zip(axes, results.values()):
        for name, run in res.runs.items():
            if name == "qsd_wrong":
                continue
            ax.plot(run.t, run.err_urad, label=name, color=colors[name], lw=1.1)
        ax.plot(
            res.runs["qsd"].t,
            res.runs["qsd"].iss_bound_urad,
            "--",
            color="#d62728",
            alpha=0.6,
            lw=1.0,
            label="ISS bound",
        )
        ax.set_ylabel("pointing residual (μrad)")
        ax.set_title(res.scenario)
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(True, alpha=0.3)
    axes[-1].set_xlabel("t (s)")
    fig.tight_layout()
    fig.savefig(fig_dir / "pointing_residual.png", dpi=140)
    plt.close(fig)

    # Availability / RMS bars
    fig, ax = plt.subplots(figsize=(8.5, 4.0))
    labels = []
    qsd_av, pid_av, open_av = [], [], []
    for res in results.values():
        labels.append(res.scenario)
        qsd_av.append(res.runs["qsd"].availability * 100)
        pid_av.append(res.runs["pid"].availability * 100)
        open_av.append(res.runs["open"].availability * 100)
    x = np.arange(len(labels))
    w = 0.25
    ax.bar(x - w, open_av, w, label="open", color=colors["open"])
    ax.bar(x, pid_av, w, label="pid", color=colors["pid"])
    ax.bar(x + w, qsd_av, w, label="qsd", color=colors["qsd"])
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("availability (%)")
    ax.set_ylim(0, 105)
    ax.legend()
    ax.set_title("Link availability (SNR ≥ 6 dB) — simulation")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(fig_dir / "availability.png", dpi=140)
    plt.close(fig)

    # Phase potential with boresight well marked
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    th = np.linspace(-0.2, 1.6, 400)
    ax.plot(np.degrees(th), phase_potential(th), color="#222222")
    ax.axvline(np.degrees(THETA_STAR), color="#d62728", ls="--", label="θ* well (boresight map)")
    ax.axvline(3 * np.degrees(THETA_STAR), color="#ff7f0e", ls=":", label="3θ* basin edge")
    ax.set_xlabel("Θ (deg)")
    ax.set_ylabel("V(Θ)")
    ax.set_title("Control Lyapunov potential (not a physical beam angle)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(fig_dir / "phase_potential.png", dpi=140)
    plt.close(fig)


class OpticalLink:
    """One-hop simulated optical link with a chosen PAT controller."""

    def __init__(
        self,
        scenario: ScenarioName = ScenarioName.ISL,
        controller: ControllerName = ControllerName.QSD,
        seed: int = 0,
        duration_s: float = 2.0,
    ):
        self.result = run_scenario(scenario, duration_s=duration_s, seed=seed)
        self.controller = controller
        self.run = self.result.runs[controller.value]
        # Start on-station (after the acquisition transient), not at t=0
        self._i = max(0, len(self.run.ber) // 2)

    def instantaneous_ber(self) -> float:
        return float(self.run.ber[min(self._i, len(self.run.ber) - 1)])

    def step(self) -> float:
        self._i = min(self._i + 1, len(self.run.ber) - 1)
        return self.instantaneous_ber()
