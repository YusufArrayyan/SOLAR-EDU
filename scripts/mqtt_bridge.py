"""Jembatan MQTT -> API (F01). Topik: solar/<kode-perangkat>, payload JSON:
{"waktu": "2026-10-15T08:01:00+07:00", "beban_kw": 12.3}  atau  {"waktu": ..., "produksi_pv_kw": 8.1}
Pembacaan dikirim per batch tiap 30 detik. Batch yang gagal dikirim disimpan dan dicoba lagi.
"""
import json
import os
import threading
import time

import httpx
import paho.mqtt.client as mqtt

API = os.getenv("API_URL", "http://localhost:8080/api/ingest")
TOKEN = os.getenv("INGEST_TOKEN", "dev-ingest-token")
antrean: list[dict] = []
kunci = threading.Lock()


def on_message(_c, _u, msg):
    try:
        data = json.loads(msg.payload)
        data["perangkat"] = msg.topic.removeprefix("solar/")
        with kunci:
            antrean.append(data)
    except (ValueError, TypeError):
        print("payload tidak valid:", msg.topic)


def kirim_berkala():
    while True:
        time.sleep(30)
        with kunci:
            batch, antrean[:] = antrean[:10000], antrean[10000:]
        if not batch:
            continue
        try:
            r = httpx.post(API, json=batch, headers={"X-Ingest-Token": TOKEN}, timeout=20)
            r.raise_for_status()
            print("terkirim", r.json())
        except httpx.HTTPError as e:
            print("gagal kirim, dicoba lagi:", e)
            with kunci:
                antrean[:0] = batch


def main():
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if os.getenv("MQTT_USER"):
        c.username_pw_set(os.getenv("MQTT_USER"), os.getenv("MQTT_PASSWORD"))
    c.on_connect = lambda cl, *_: cl.subscribe("solar/#", qos=1)
    c.on_message = on_message
    c.connect(os.getenv("MQTT_HOST", "localhost"), int(os.getenv("MQTT_PORT", "1883")))
    threading.Thread(target=kirim_berkala, daemon=True).start()
    c.loop_forever()


if __name__ == "__main__":
    main()
