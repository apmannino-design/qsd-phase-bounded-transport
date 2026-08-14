"""Keplerian circular-orbit geometry for LEO–LEO ISL and LEO–ground passes."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aurora_qsd.optical.constants import GM_EARTH, OMEGA_EARTH, R_EARTH


@dataclass(frozen=True)
class CircularOrbit:
    """Inertial circular orbit in a single plane (ECI, z unused = 0 for ISL)."""

    altitude_m: float
    inclination_rad: float
    raan_rad: float
    arg_lat0_rad: float  # argument of latitude at t=0

    @property
    def radius_m(self) -> float:
        return R_EARTH + self.altitude_m

    @property
    def mean_motion(self) -> float:
        return float(np.sqrt(GM_EARTH / self.radius_m**3))

    @property
    def period_s(self) -> float:
        return float(2.0 * np.pi / self.mean_motion)

    def position_velocity(self, t: float) -> tuple[np.ndarray, np.ndarray]:
        """Return ECI position (m) and velocity (m/s) at time t."""
        u = self.arg_lat0_rad + self.mean_motion * t
        ci, si = np.cos(self.inclination_rad), np.sin(self.inclination_rad)
        cr, sr = np.cos(self.raan_rad), np.sin(self.raan_rad)
        cu, su = np.cos(u), np.sin(u)
        # R3(Ω) R1(i) R3(u): circular, so perifocal x is along the radius
        r3_raan = np.array([[cr, -sr, 0.0], [sr, cr, 0.0], [0.0, 0.0, 1.0]])
        r1_inc = np.array([[1.0, 0.0, 0.0], [0.0, ci, -si], [0.0, si, ci]])
        r3_u = np.array([[cu, -su, 0.0], [su, cu, 0.0], [0.0, 0.0, 1.0]])
        rot = r3_raan @ r1_inc @ r3_u
        r = rot @ np.array([self.radius_m, 0.0, 0.0])
        v = rot @ np.array([0.0, self.radius_m * self.mean_motion, 0.0])
        return r, v


def circular_orbit(
    altitude_km: float = 550.0,
    inclination_deg: float = 97.6,
    raan_deg: float = 0.0,
    arg_lat0_deg: float = 0.0,
) -> CircularOrbit:
    return CircularOrbit(
        altitude_m=altitude_km * 1e3,
        inclination_rad=np.radians(inclination_deg),
        raan_rad=np.radians(raan_deg),
        arg_lat0_rad=np.radians(arg_lat0_deg),
    )


@dataclass(frozen=True)
class GroundStation:
    name: str
    lat_deg: float
    lon_deg: float
    alt_m: float

    def eci_position(self, t: float) -> np.ndarray:
        lat = np.radians(self.lat_deg)
        lon = np.radians(self.lon_deg) + OMEGA_EARTH * t
        n = R_EARTH  # spherical
        cl, sl = np.cos(lat), np.sin(lat)
        co, so = np.cos(lon), np.sin(lon)
        r = n + self.alt_m
        return np.array([r * cl * co, r * cl * so, r * sl])


# NASA OGS-class high-altitude site (Haleakalā, Maui)
HALEAKALA = GroundStation("Haleakala", 20.708, -156.257, 3055.0)


@dataclass(frozen=True)
class LinkGeometry:
    t: float
    range_m: float
    range_rate_m_s: float
    los_eci: np.ndarray
    elevation_deg: float
    doppler_hz: float

    @property
    def in_view(self) -> bool:
        return self.elevation_deg > 0.0


def _los_geometry(
    r_tx: np.ndarray,
    v_tx: np.ndarray,
    r_rx: np.ndarray,
    v_rx: np.ndarray,
    wavelength_m: float,
    rx_up: np.ndarray | None,
) -> LinkGeometry:
    dr = r_rx - r_tx
    range_m = float(np.linalg.norm(dr))
    los = dr / range_m
    dv = v_rx - v_tx
    range_rate = float(np.dot(dv, los))
    doppler = -range_rate / wavelength_m  # Hz, optical carrier
    if rx_up is None:
        el = 90.0  # vacuum ISL: treat as always "overhead"
    else:
        up = rx_up / np.linalg.norm(rx_up)
        # los is tx→rx; satellite elevation at a ground receiver is −los vs zenith
        to_sat = -los
        el = float(np.degrees(np.arcsin(np.clip(np.dot(to_sat, up), -1.0, 1.0))))
    return LinkGeometry(
        t=0.0,
        range_m=range_m,
        range_rate_m_s=range_rate,
        los_eci=los,
        elevation_deg=el,
        doppler_hz=doppler,
    )


def intersat_geometry(
    tx: CircularOrbit,
    rx: CircularOrbit,
    t: float,
    wavelength_m: float,
) -> LinkGeometry:
    r_tx, v_tx = tx.position_velocity(t)
    r_rx, v_rx = rx.position_velocity(t)
    geo = _los_geometry(r_tx, v_tx, r_rx, v_rx, wavelength_m, rx_up=None)
    return LinkGeometry(
        t=t,
        range_m=geo.range_m,
        range_rate_m_s=geo.range_rate_m_s,
        los_eci=geo.los_eci,
        elevation_deg=90.0,
        doppler_hz=geo.doppler_hz,
    )


def leo_ground_geometry(
    sat: CircularOrbit,
    gs: GroundStation,
    t: float,
    wavelength_m: float,
) -> LinkGeometry:
    r_sat, v_sat = sat.position_velocity(t)
    r_gs = gs.eci_position(t)
    v_gs = np.cross(np.array([0.0, 0.0, OMEGA_EARTH]), r_gs)
    geo = _los_geometry(r_sat, v_sat, r_gs, v_gs, wavelength_m, rx_up=r_gs)
    return LinkGeometry(
        t=t,
        range_m=geo.range_m,
        range_rate_m_s=geo.range_rate_m_s,
        los_eci=geo.los_eci,
        elevation_deg=geo.elevation_deg,
        doppler_hz=geo.doppler_hz,
    )


def station_under(orbit: CircularOrbit, t: float = 0.0, alt_m: float = 3055.0) -> GroundStation:
    """Place an OGS at the sub-satellite point (Haleakalā-class altitude)."""
    r, _ = orbit.position_velocity(t)
    lat = float(np.degrees(np.arcsin(np.clip(r[2] / np.linalg.norm(r), -1.0, 1.0))))
    lon = float(np.degrees(np.arctan2(r[1], r[0]))) - np.degrees(OMEGA_EARTH * t)
    return GroundStation("subpoint-ogs", lat, lon, alt_m)


def sample_geometry(
    kind: str,
    t: np.ndarray,
    wavelength_m: float,
    altitude_km: float = 550.0,
    anomaly_offset_deg: float = 20.0,
    gs: GroundStation | None = None,
    arg_lat0_deg: float = 0.0,
) -> list[LinkGeometry]:
    """Sample ISL or downlink geometry on a time grid.

    Downlink default: OGS at the t=0 sub-satellite point so a 4 s snapshot
    is a high-elevation pass, not a miss of Haleakalā.
    """
    tx = circular_orbit(altitude_km=altitude_km, arg_lat0_deg=arg_lat0_deg)
    if kind == "isl":
        rx = circular_orbit(
            altitude_km=altitude_km, arg_lat0_deg=arg_lat0_deg + anomaly_offset_deg
        )
        return [intersat_geometry(tx, rx, float(ti), wavelength_m) for ti in t]
    sat = circular_orbit(altitude_km=altitude_km, arg_lat0_deg=arg_lat0_deg)
    if gs is None:
        gs = station_under(sat, t=0.0)
    return [leo_ground_geometry(sat, gs, float(ti), wavelength_m) for ti in t]
