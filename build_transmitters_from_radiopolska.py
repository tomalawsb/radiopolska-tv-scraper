#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Konwerter eksportu RadioPolska DVB-T/T2 do data/transmitters.json aplikacji DVB-T/T2 Point.
Wejście: emisje_dvbt.json wygenerowany scraperem.
Wyjście: data/transmitters.json z pogrupowanymi obiektami nadawczymi i muxami.
"""
from __future__ import annotations

import json
import math
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

APP_DATA_VERSION = "19.3 - 1705261535"


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def number(value: object, default=None):
    text = clean_text(value).replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    if not m:
        return default
    try:
        return float(m.group(0))
    except ValueError:
        return default


def dms_to_decimal(text: str):
    text = clean_text(text)
    pattern = re.compile(
        r"(\d{1,3})°\s*(\d{1,2})'\s*(\d+(?:[,.]\d+)?)\"\s*([NS])\s*,\s*"
        r"(\d{1,3})°\s*(\d{1,2})'\s*(\d+(?:[,.]\d+)?)\"\s*([EW])",
        re.I,
    )
    m = pattern.search(text)
    if not m:
        return None, None
    lat = int(m.group(1)) + int(m.group(2)) / 60 + float(m.group(3).replace(",", ".")) / 3600
    lon = int(m.group(5)) + int(m.group(6)) / 60 + float(m.group(7).replace(",", ".")) / 3600
    if m.group(4).upper() == "S":
        lat = -lat
    if m.group(8).upper() == "W":
        lon = -lon
    return round(lat, 7), round(lon, 7)


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return text or "tx"


def clean_mux_name(raw: str, uwagi: str) -> str:
    raw = clean_text(raw)
    m = re.search(r"MUX(?:-L)?\d+|MUX-[0-9A-Za-z]+", raw, re.I)
    if m:
        return m.group(0).upper()
    m = re.search(r"MUX(?:-L)?\d+|MUX-[0-9A-Za-z]+", uwagi, re.I)
    return m.group(0).upper() if m else "MUX"


def parse_location_site(uwagi: str, mux_name: str):
    uwagi = clean_text(uwagi)
    site = ""
    location = ""
    m = re.search(r"k\.\s*\d+\s+(.*?)\s+\*([^*]+)\*\s+[A-Z]{3}\s+[0-9,.]+\s+[HV]", uwagi)
    if m:
        before_star = clean_text(m.group(1))
        site = clean_text(m.group(2))
        location = clean_text(re.sub(r"^" + re.escape(mux_name) + r"\b", "", before_star, flags=re.I))
        location = clean_text(re.sub(r"^MUX(?:-L)?\d+\b", "", location, flags=re.I))
    if not site:
        m = re.search(r"\*([^*]+)\*", uwagi)
        site = clean_text(m.group(1)) if m else "Obiekt nadawczy"
    if not location:
        location = site
    return location, site


def clean_antenna_name(text: str) -> str:
    text = clean_text(text)
    text = text.split("Konfiguracja systemu antenowego:", 1)[0]
    text = text.split("Operator", 1)[0]
    return clean_text(text)


def clean_antenna_config(text: str) -> str:
    text = clean_text(text)
    text = text.split("Operator", 1)[0]
    return clean_text(text)


def band_from_freq(freq: float | None) -> str:
    if freq is None:
        return "—"
    return "VHF" if freq < 300 else "UHF"


def is_directional(row: dict) -> str:
    blob = (clean_text(row.get("Kierunek")) + " " + clean_text(row.get("Wysokosc_anteny"))).lower()
    if "dookólna" in blob:
        return "dookólna"
    if "kierunkowa" in blob:
        return "kierunkowa"
    return "nieokreślona"


def load_rows(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("emisje", "data", "rows", "items"):
            if isinstance(data.get(key), list):
                return data[key]
    raise ValueError("Nie rozpoznano struktury pliku RadioPolska JSON.")


def build(input_path: Path) -> dict:
    rows = load_rows(input_path)
    groups = defaultdict(list)
    skipped = 0
    for row in rows:
        lat, lon = dms_to_decimal(row.get("Wspolrzedne", ""))
        if lat is None or lon is None:
            skipped += 1
            continue
        groups[(lat, lon)].append(row)

    transmitters = []
    used_ids = set()
    for (lat, lon), items in sorted(groups.items(), key=lambda x: (x[0][0], x[0][1])):
        first = items[0]
        mux_first = clean_mux_name(first.get("Multiplex", ""), first.get("Uwagi", ""))
        location, site = parse_location_site(first.get("Uwagi", ""), mux_first)
        base_name = f"{location} / {site}" if site and site.lower() not in location.lower() else location
        base_name = clean_text(base_name)
        tx_id_base = slugify(base_name)
        tx_id = tx_id_base
        suffix = 2
        while tx_id in used_ids:
            tx_id = f"{tx_id_base}-{suffix}"
            suffix += 1
        used_ids.add(tx_id)

        site_elevations = [number(r.get("Wysokosc_NPM")) for r in items]
        site_elevations = [x for x in site_elevations if x is not None]
        antenna_heights = [number(r.get("Wysokosc_anteny")) for r in items]
        antenna_heights = [x for x in antenna_heights if x is not None]

        muxes = []
        links = []
        for r in items:
            freq = number(r.get("MHz"))
            erp = number(r.get("ERP_kW"))
            mux = clean_mux_name(r.get("Multiplex", ""), r.get("Uwagi", ""))
            _, mux_site = parse_location_site(r.get("Uwagi", ""), mux)
            ant_name = clean_antenna_name(r.get("Nazwa_anteny"))
            ant_cfg = clean_antenna_config(r.get("Typ_konfiguracji"))
            ant_h = number(r.get("Wysokosc_anteny"))
            link_ant = clean_text(r.get("Link_ANT"))
            link_emisji = clean_text(r.get("Link_emisji"))
            if link_ant:
                links.append(link_ant)
            muxes.append({
                "name": mux,
                "channel": f"K{int(number(r.get('Kanal'), 0))}" if number(r.get("Kanal")) is not None else "—",
                "channel_no": int(number(r.get("Kanal"), 0)) if number(r.get("Kanal")) is not None else None,
                "frequency_mhz": freq,
                "erp_kw": erp,
                "polarization": clean_text(r.get("Pol")) or "—",
                "band": band_from_freq(freq),
                "pattern": is_directional(r),
                "antenna_height_m": ant_h,
                "antenna_name": ant_name,
                "antenna_config": ant_cfg,
                "operator": clean_text(r.get("Operator")),
                "voivodeship_code": clean_text(r.get("Woj")),
                "site_name_from_row": mux_site,
                "radiopolska_emission_url": link_emisji,
                "ant_file_url": link_ant,
            })

        muxes.sort(key=lambda m: (m.get("name") or "", m.get("channel_no") or 0, -(m.get("erp_kw") or 0)))
        transmitters.append({
            "id": tx_id,
            "name": base_name,
            "short_name": site or base_name,
            "location": location,
            "site": site,
            "lat": lat,
            "lon": lon,
            "site_elevation_m": round(sum(site_elevations) / len(site_elevations), 2) if site_elevations else None,
            "mast_height_m": max(antenna_heights) if antenna_heights else 60,
            "height_source": "RadioPolska: n.p.t. z emisji; przyjęto maksymalną wysokość anteny dla obiektu",
            "source": "RadioPolska wykaz TV — eksport użytkownika, oczyszczony lokalnie",
            "radiopolska_ant_files": sorted(set(links)),
            "muxes": muxes,
        })

    return {
        "version": APP_DATA_VERSION,
        "source": "RadioPolska wykaz TV — emisje DVB-T/T2, eksport użytkownika oczyszczony konwerterem",
        "updated_at": datetime.now().strftime("%Y-%m-%d"),
        "license_note": "Dane źródłowe wymagają zachowania warunków licencji RadioPolska/CC BY 4.0 i podania źródła przy publikacji.",
        "is_demo": False,
        "input_rows": len(rows),
        "skipped_rows_without_coordinates": skipped,
        "transmitters_count": len(transmitters),
        "note": "Obiekty pogrupowano po współrzędnych. Dane tekstowe oczyszczono ze stopek, formularzy i komunikatów strony. Pliki .ant nie są pobierane automatycznie — zapisano tylko linki.",
        "transmitters": transmitters,
    }


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("Użycie: python build_transmitters_from_radiopolska.py emisje_dvbt.json data/transmitters.json")
        return 2
    src = Path(argv[1])
    dst = Path(argv[2])
    result = build(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {result['input_rows']} emisji -> {result['transmitters_count']} obiektów, pominięto {result['skipped_rows_without_coordinates']} bez współrzędnych")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
