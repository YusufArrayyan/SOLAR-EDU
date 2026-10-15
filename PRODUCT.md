# Product

## Register

product

## Platform

web

## Users

Primary: the building manager (pengelola gedung) of one pilot building at Universitas Bengkulu. A technician or building staff member, coached by a lecturer, who glances at the screen between other work. Numbers and warnings must read at a glance; every recommendation must state its reason.

Secondary roles, each with a scoped view:
- Mahasiswa piket: students on daily or weekly duty. They see a short task list, deadlines, and a way to mark tasks done with proof.
- Tim pengelola: supervising lecturer and student admins. They maintain parameters, schedules, users, and reports.
- Pimpinan kampus: dean, vice rector, facilities unit. They read verifiable impact and the leaderboard to decide on expansion.
- Mahasiswa dan dosen: building users and researchers. They use aggregate datasets and practicum modules.

## Product Purpose

SOLAR-EDU AI reads a campus building's electricity consumption and solar production, forecasts load 24 hours ahead with Random Forest, flags waste from forecast residuals, and turns findings into recommendations that a human always verifies before anything happens. Success: one building can measure, predict, and reduce its electricity waste, and the process becomes learning material for students.

## Positioning

AI proposes, people decide: every finding becomes a reasoned recommendation with a verification trail, a duty task, and a measured 14-day evaluation.

## Brand Personality

Honest, calm, instructive. It reports results as they are (simulated data is always labelled, savings targets are not claimed before a baseline exists).

## Anti-references

- Gamified energy apps with confetti, badges, and inflated savings claims.
- Generic SaaS hero-metric dashboards with gradient accents.
- Control-panel UIs that imply the system switches devices on its own (it never does).

## Design Principles

1. One screen answers one question. Ringkasan: "what do I need to do today". Dampak: "what was the result".
2. Urgent first: anomaly warnings on top, four key figures, then charts.
3. Color has fixed meaning: blue = prediction, amber = solar production, red = anomaly only. Color is never the only signal; anomalies carry a text label.
4. Role decides content: duty students see only their tasks; leadership sees impact and the leaderboard.
5. Indonesian interface language, sentence case, standard terms (Masuk, Keluar, Simpan, Batal, Ubah, Pengaturan, Unduh).

## Accessibility & Inclusion

WCAG 2.2 AA text contrast, full keyboard operation, charts with text alternatives and arrow-key exploration, prefers-reduced-motion respected, works at 360 px width without horizontal scroll, 44 px touch targets on touch screens.
