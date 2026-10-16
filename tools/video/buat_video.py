"""Buat video panduan SOLAR-EDU AI: rekaman layar aplikasi sungguhan + narasi ElevenLabs + teks keterangan.

    python tools/video/buat_video.py              # narasi ElevenLabs (butuh ELEVENLABS_API_KEY)
    python tools/video/buat_video.py --tanpa-suara

Keluaran: frontend/assets/video/panduan.mp4, panduan.vtt, panduan-poster.jpg.
Rekaman memakai server lokal mode simulasi (data contoh), bukan server produksi.

Variabel opsional: ELEVENLABS_VOICE_ID, ELEVENLABS_MODEL (bawaan eleven_multilingual_v2),
CHROMIUM_PATH (bila Chromium bawaan Playwright tidak cocok).
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import imageio_ffmpeg
from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "frontend" / "assets" / "video"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
PORT = 8099
BASE = f"http://127.0.0.1:{PORT}"
LEBAR, TINGGI = 1280, 720

NARASI = [
    ("pembuka", "SOLAR-EDU AI membantu gedung kampus menekan pemborosan listrik. Sistem membaca meter listrik dan "
                "panel surya, memprediksi beban, lalu mengusulkan tindakan. Keputusannya tetap di tangan manusia."),
    ("masuk", "Masuk dengan email kampus dan kata sandi dari tim pengelola. Menu yang tampil menyesuaikan peran "
              "masing-masing."),
    ("ringkasan", "Halaman Ringkasan menjawab satu pertanyaan: apa yang perlu dilakukan hari ini. Peringatan anomali "
                  "selalu berada paling atas, lalu empat angka utama."),
    ("grafik", "Garis hitam adalah beban aktual, garis biru prediksi beserta rentangnya, dan area kuning produksi panel "
               "surya. Jam anomali ditandai merah, lengkap dengan labelnya."),
    ("rekomendasi", "Menu Rekomendasi berisi usulan sistem. Setiap usulan menyebut alasan, lokasi panel, dan perkiraan "
                    "energi yang bisa dihemat."),
    ("verifikasi", "Di halaman detail, periksa alasan dan grafiknya. Kalau masuk akal, pilih mahasiswa piket dan batas "
                   "waktu, lalu tekan Verifikasi rekomendasi. Kalau tidak, tolak dengan alasan, dan alasan itu dipakai "
                   "untuk memperbaiki ambang deteksi."),
    ("piket", "Mahasiswa piket melihat tugasnya di menu Tugas dan rekomendasi. Setelah mengecek ruangan, tekan Tandai "
              "sudah dilaksanakan, lalu tulis catatan bukti."),
    ("pemantauan", "Sejak itu sistem memantau konsumsi selama empat belas hari. Pengelola kemudian mencatat hasilnya, "
                   "dibandingkan dengan gedung pembanding."),
    ("dampak", "Pimpinan kampus membuka Dampak untuk melihat penghematan terukur, biaya dan emisi yang terhindarkan, "
               "serta indikator keberhasilan."),
    ("peringkat", "Papan peringkat membandingkan efisiensi antargedung memakai indeks yang adil terhadap luas dan jam "
                  "operasional."),
    ("pengaturan", "Tim pengelola menyiapkan sistem di Pengaturan: data gedung, perangkat meter, ruang, jadwal kuliah, "
                   "dan akun pengguna. Pada pemasangan baru, Ringkasan menampilkan daftar persiapan sampai semua langkah "
                   "selesai."),
    ("penutup", "Mahasiswa dan dosen dapat mengunduh dataset dan mengikuti modul praktikum di Pusat belajar. Langkah "
                "tertulis untuk setiap peran tersedia di menu Panduan."),
]

EMAIL = {"pengelola": "pengelola@solar-edu.test", "tim": "tim@solar-edu.test", "pimpinan": "pimpinan@solar-edu.test",
         "Nadia Putri": "nadia.piket@solar-edu.test", "Bima Saputra": "bima.piket@solar-edu.test",
         "Sari Wulandari": "sari.piket@solar-edu.test"}

# Kursor tiruan agar gerakan dan klik terlihat di rekaman; elemen khusus akun uji disembunyikan.
INIT = """
(() => {
  const pasang = () => {
    if (document.getElementById('kursor-video')) return;
    const st = document.createElement('style');
    st.textContent = `.demo{display:none!important}
      #kursor-video{position:fixed;left:0;top:0;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;
        background:rgba(0,112,243,.25);border:2px solid #0070f3;z-index:99999;pointer-events:none;
        transition:transform .12s ease-out}
      #kursor-video.klik{transform:scale(.6);background:rgba(0,112,243,.55)}`;
    document.head.append(st);
    const k = document.createElement('div'); k.id = 'kursor-video'; document.body.append(k);
    addEventListener('mousemove', (e) => { k.style.left = e.clientX + 'px'; k.style.top = e.clientY + 'px'; }, true);
    addEventListener('mousedown', () => k.classList.add('klik'), true);
    addEventListener('mouseup', () => k.classList.remove('klik'), true);
    new MutationObserver(() => {
      const p = document.getElementById('user-peran');
      if (p && p.textContent.includes(' · akun demo')) p.textContent = p.textContent.replace(' · akun demo', '');
    }).observe(document.documentElement, { subtree: true, childList: true, characterData: true });
  };
  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', pasang); else pasang();
})();
"""


# ---------------------------------------------------------------- utilitas
def durasi_media(path: Path) -> float:
    r = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def kunci_elevenlabs() -> str:
    k = os.environ.get("ELEVENLABS_API_KEY", "")
    if not k and sys.platform == "win32":  # setx menyimpan ke registri pengguna
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "[Environment]::GetEnvironmentVariable('ELEVENLABS_API_KEY','User')"],
                           capture_output=True, text=True)
        k = r.stdout.strip()
    return k


def pilih_suara(c: httpx.Client) -> str:
    if os.environ.get("ELEVENLABS_VOICE_ID"):
        return os.environ["ELEVENLABS_VOICE_ID"]
    suara = c.get("https://api.elevenlabs.io/v1/voices").raise_for_status().json()["voices"]
    for v in suara:  # utamakan suara berlabel bahasa Indonesia
        label = json.dumps(v.get("labels", {})).lower() + v.get("name", "").lower()
        if "indonesia" in label or '"id"' in label:
            return v["voice_id"]
    return suara[0]["voice_id"]


def buat_narasi(kerja: Path) -> dict[str, Path]:
    kunci = kunci_elevenlabs()
    if not kunci:
        raise SystemExit("ELEVENLABS_API_KEY belum disetel. Jalankan: setx ELEVENLABS_API_KEY \"<key>\", "
                         "buka terminal baru, lalu ulangi. Atau pakai --tanpa-suara.")
    model = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    hasil = {}
    with httpx.Client(headers={"xi-api-key": kunci}, timeout=120) as c:
        suara = pilih_suara(c)
        print(f"Narasi ElevenLabs: suara {suara}, model {model}")
        for kode, teks in NARASI:
            f = kerja / f"{kode}.mp3"
            r = c.post(f"https://api.elevenlabs.io/v1/text-to-speech/{suara}",
                       params={"output_format": "mp3_44100_128"},
                       json={"text": teks, "model_id": model, "language_code": "id",
                             "voice_settings": {"stability": 0.55, "similarity_boost": 0.75, "style": 0.1}})
            if r.status_code == 400 and "language_code" in r.text:  # model lama tidak menerima language_code
                r = c.post(f"https://api.elevenlabs.io/v1/text-to-speech/{suara}",
                           params={"output_format": "mp3_44100_128"},
                           json={"text": teks, "model_id": model,
                                 "voice_settings": {"stability": 0.55, "similarity_boost": 0.75}})
            if r.status_code != 200:
                raise SystemExit(f"ElevenLabs menolak permintaan ({r.status_code}): {r.text[:300]}")
            f.write_bytes(r.content)
            hasil[kode] = f
            print(f"  {kode}: {durasi_media(f):.1f} s")
    return hasil


# ---------------------------------------------------------------- server contoh
def jalankan_server(data_dir: str) -> subprocess.Popen:
    env = {**os.environ, "SOLAR_SIMULATION": "1", "SOLAR_DATA_DIR": data_dir, "PORT": str(PORT),
           "HOST": "127.0.0.1", "SOLAR_JOBS": "4"}
    proc = subprocess.Popen([sys.executable, str(ROOT / "backend" / "run.py")], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(240):
        try:
            if httpx.get(BASE + "/api/sehat", timeout=2).status_code == 200:
                return proc
        except httpx.HTTPError:
            pass
        time.sleep(1)
    proc.kill()
    raise SystemExit("Server contoh tidak menyala.")


# ---------------------------------------------------------------- aksi di layar
def gerak(page: Page, selector: str, klik: bool = False, nth: int = 0):
    el = page.locator(selector).nth(nth)
    el.scroll_into_view_if_needed()
    b = el.bounding_box()
    if not b:
        return
    page.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, steps=18)
    page.wait_for_timeout(250)
    if klik:  # satu klik lewat mouse agar kursor tiruan ikut beranimasi
        page.mouse.down()
        page.mouse.up()
        page.wait_for_timeout(700)


def ketik(page: Page, selector: str, teks: str):
    gerak(page, selector, klik=True)
    page.locator(selector).fill("")
    page.locator(selector).type(teks, delay=35)


def masuk(page: Page, email: str, sandi: str):
    if page.locator("#keluar").is_visible():
        gerak(page, "#keluar", klik=True)
        page.wait_for_selector("#form-masuk")
    ketik(page, "#email", email)
    ketik(page, "#sandi", sandi)
    gerak(page, "#form-masuk button[type=submit]", klik=True)
    page.wait_for_selector("#konten h1", timeout=20000)
    page.wait_for_timeout(1200)


def gulir(page: Page, piksel: int, langkah: int = 6):
    for _ in range(langkah):
        page.mouse.wheel(0, piksel / langkah)
        page.wait_for_timeout(120)


def rekam(durasi: dict[str, float], kerja: Path) -> tuple[Path, dict[str, float], Path]:
    sandi = httpx.get(BASE + "/api/sehat").json()["demo_sandi"]
    mulai: dict[str, float] = {}
    poster = kerja / "poster.png"
    exe = os.environ.get("CHROMIUM_PATH") or next(iter(glob.glob(os.path.expandvars(
        r"%LOCALAPPDATA%\ms-playwright\chromium-*\chrome-win64\chrome.exe"))), None)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        ctx = b.new_context(viewport={"width": LEBAR, "height": TINGGI}, record_video_dir=str(kerja),
                            record_video_size={"width": LEBAR, "height": TINGGI}, locale="id-ID",
                            timezone_id="Asia/Jakarta", color_scheme="light",
                            bypass_csp=True)  # CSP aplikasi memblokir gaya kursor tiruan
        ctx.add_init_script(INIT)
        page = ctx.new_page()
        t0 = time.monotonic()

        def segmen(kode: str, aksi):
            mulai[kode] = time.monotonic() - t0
            aksi()
            sisa = durasi[kode] - (time.monotonic() - t0 - mulai[kode])
            if sisa > 0:
                page.wait_for_timeout(int(sisa * 1000))

        page.goto(BASE + "/")
        page.wait_for_selector("#form-masuk")
        page.wait_for_timeout(600)
        segmen("pembuka", lambda: gerak(page, ".masuk-art h1"))
        segmen("masuk", lambda: masuk(page, EMAIL["pengelola"], sandi))

        def ringkasan():
            gerak(page, ".alert", nth=0)
            page.wait_for_timeout(800)
            gerak(page, ".figs .fig", nth=1)
            page.screenshot(path=str(poster))
        segmen("ringkasan", ringkasan)

        def grafik():
            page.locator("#grafik").scroll_into_view_if_needed()
            b2 = page.locator("#grafik").bounding_box()
            for i in range(12):
                page.mouse.move(b2["x"] + b2["width"] * (0.1 + i * 0.07), b2["y"] + b2["height"] * 0.5, steps=6)
                page.wait_for_timeout(260)
        segmen("grafik", grafik)

        def rekomendasi():
            page.evaluate("scrollTo(0,0)")
            gerak(page, "#nav-list a[data-path=rekomendasi]", klik=True)
            page.wait_for_selector(".rec-row")
            gerak(page, ".rec-row", nth=0)
            gerak(page, ".tabs a[href*=Diusulkan]", klik=True)
            page.wait_for_selector(".rec-row")
        segmen("rekomendasi", rekomendasi)

        pelaksana = {}

        def verifikasi():
            gerak(page, ".rec-row", nth=0, klik=True)
            page.wait_for_selector("#f-verif")
            gerak(page, "#h-alasan")
            page.wait_for_timeout(900)
            gerak(page, "#pelaksana")
            pelaksana["nama"] = page.locator("#pelaksana option:checked").inner_text().split(" · ")[0]
            pelaksana["id"] = page.url.split("/")[-1]
            gerak(page, "#batas")
            page.select_option("#batas", "48")
            gerak(page, "#f-verif button[type=submit]", klik=True)
            page.wait_for_selector("#h-tugas", timeout=15000)
            page.wait_for_timeout(600)
        segmen("verifikasi", verifikasi)

        def piket():
            page.evaluate("scrollTo(0,0)")
            masuk(page, EMAIL.get(pelaksana.get("nama", ""), EMAIL["Bima Saputra"]), sandi)
            gerak(page, "[data-buka]", nth=0, klik=True)
            page.locator("form[id^=form-] textarea").first.type(
                "Lampu lobi dan pompa air sudah dimatikan pukul 19.10, dicatat di buku piket.", delay=18)
            gerak(page, "form[id^=form-] button[type=submit]", nth=0, klik=True)
            page.wait_for_timeout(900)
        segmen("piket", piket)

        def pemantauan():
            if pelaksana.get("id"):
                page.goto(BASE + "/#/rekomendasi/" + pelaksana["id"])
                page.wait_for_selector("#konten h1")
                page.wait_for_timeout(500)
            gerak(page, ".steps")
            if page.locator("#h-pantau").count():
                gerak(page, "#h-pantau")
        segmen("pemantauan", pemantauan)

        def dampak():
            page.evaluate("scrollTo(0,0)")
            masuk(page, EMAIL["pimpinan"], sandi)
            gerak(page, ".figs .fig", nth=0)
            gerak(page, ".figs .fig", nth=2)
            gulir(page, 520)
            page.wait_for_timeout(700)
            gulir(page, 700)
        segmen("dampak", dampak)

        def peringkat():
            page.evaluate("scrollTo(0,0)")
            gerak(page, "#nav-list a[data-path=peringkat]", klik=True)
            page.wait_for_selector("table")
            gerak(page, "tr.me")
        segmen("peringkat", peringkat)

        def pengaturan():
            page.evaluate("scrollTo(0,0)")
            masuk(page, EMAIL["tim"], sandi)
            gerak(page, "#nav-list a[data-path=pengaturan]", klik=True)
            page.wait_for_selector("#f-param")
            for tab in ("gedung", "jadwal", "pengguna"):
                gerak(page, f".tabs a[href$='tab={tab}']", klik=True)
                page.wait_for_timeout(1300)
        segmen("pengaturan", pengaturan)

        def penutup():
            page.evaluate("scrollTo(0,0)")
            gerak(page, "#nav-list a[data-path=belajar]", klik=True)
            page.wait_for_selector("#h-data")
            page.wait_for_timeout(1200)
            gerak(page, "#nav-list a[data-path=panduan]", klik=True)
            page.wait_for_timeout(1500)
        segmen("penutup", penutup)
        page.wait_for_timeout(800)
        total = time.monotonic() - t0
        video = Path(page.video.path())
        ctx.close()
        b.close()
    mulai["_total"] = total
    return video, mulai, poster


# ---------------------------------------------------------------- penyusunan
def detik_vtt(s: float) -> str:
    j, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{int(j):02d}:{int(m):02d}:{s:06.3f}"


def potong_kalimat(teks: str, maks: int = 84) -> list[str]:
    kata, baris, out = teks.split(), "", []
    for k in kata:
        if len(baris) + len(k) + 1 > maks and baris:
            out.append(baris)
            baris = k
        else:
            baris = f"{baris} {k}".strip()
        if baris.endswith((".", ":", ",")) and len(baris) > maks * 0.55:
            out.append(baris)
            baris = ""
    if baris:
        out.append(baris)
    return out


def tulis_vtt(mulai: dict[str, float], durasi: dict[str, float], path: Path):
    isi = ["WEBVTT", "", "NOTE Panduan SOLAR-EDU AI. Tampilan memakai data contoh.", ""]
    no = 1
    for kode, teks in NARASI:
        potong = potong_kalimat(teks)
        total_kar = sum(len(x) for x in potong)
        t = mulai[kode] + 0.25
        for p in potong:
            d = durasi[kode] * len(p) / total_kar
            isi += [str(no), f"{detik_vtt(t)} --> {detik_vtt(t + d)}", p, ""]
            t += d
            no += 1
    path.write_text("\n".join(isi), encoding="utf-8")


def susun(video: Path, mulai: dict[str, float], audio: dict[str, Path] | None, keluar: Path):
    total = mulai["_total"]
    if not audio:
        subprocess.run([FFMPEG, "-y", "-i", str(video), "-c:v", "libx264", "-preset", "slow", "-crf", "28",
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(keluar)], check=True,
                       capture_output=True)
        return
    args = [FFMPEG, "-y", "-i", str(video)]
    for kode, _ in NARASI:
        args += ["-i", str(audio[kode])]
    filt = []
    for i, (kode, _) in enumerate(NARASI, start=1):
        ms = int((mulai[kode] + 0.25) * 1000)
        filt.append(f"[{i}:a]adelay={ms}|{ms},aformat=channel_layouts=stereo[a{i}]")
    filt.append("".join(f"[a{i}]" for i in range(1, len(NARASI) + 1))
                + f"amix=inputs={len(NARASI)}:normalize=0,apad,atrim=0:{total:.2f},loudnorm=I=-16:TP=-1.5[aout]")
    args += ["-filter_complex", ";".join(filt), "-map", "0:v", "-map", "[aout]", "-c:v", "libx264", "-preset", "slow",
             "-crf", "28", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
             "-shortest", str(keluar)]
    subprocess.run(args, check=True, capture_output=True)


def main():
    tanpa_suara = "--tanpa-suara" in sys.argv
    kerja = Path(tempfile.mkdtemp(prefix="solar-video-"))
    data_dir = tempfile.mkdtemp(prefix="solar-video-data-")
    audio = None if tanpa_suara else buat_narasi(kerja)
    durasi = {k: (durasi_media(audio[k]) if audio else max(4.0, len(t) / 14.0)) + 0.9 for k, t in NARASI}
    print("Menyalakan server contoh (mengisi data simulasi)…")
    server = jalankan_server(data_dir)
    try:
        print("Merekam layar…")
        video, mulai, poster = rekam(durasi, kerja)
    finally:
        server.terminate()
    OUT.mkdir(parents=True, exist_ok=True)
    print("Menyusun video…")
    susun(video, mulai, audio, OUT / "panduan.mp4")
    tulis_vtt(mulai, durasi, OUT / "panduan.vtt")
    subprocess.run([FFMPEG, "-y", "-i", str(poster), "-q:v", "4", str(OUT / "panduan-poster.jpg")], check=True,
                   capture_output=True)
    print(f"Selesai: {OUT / 'panduan.mp4'} ({durasi_media(OUT / 'panduan.mp4'):.0f} s, "
          f"{(OUT / 'panduan.mp4').stat().st_size / 2**20:.1f} MB), {'tanpa suara' if not audio else 'dengan narasi'}")
    shutil.rmtree(kerja, ignore_errors=True)
    shutil.rmtree(data_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
