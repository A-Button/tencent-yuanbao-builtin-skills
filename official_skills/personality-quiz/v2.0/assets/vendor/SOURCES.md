# Offline runtime assets

These dependencies are bundled locally; the generated page never requests them from a CDN.

- html2canvas 1.4.1: https://github.com/niklasvh/html2canvas — MIT, see `html2canvas.LICENSE`. Used only for user-triggered local PNG generation.
- Tabler Icons 3.34.1: https://github.com/tabler/tabler-icons — MIT, see `tabler.LICENSE`. Original check outline and filled pin in `../check.svg` and `../pin.svg`; colors are applied during embedding.
- Barlow Condensed ExtraBold Italic: https://github.com/google/fonts/tree/main/ofl/barlowcondensed — SIL Open Font License, see `BarlowCondensed.OFL.txt`. Used for the four-letter report title; the font remains unmodified.
- Report art: the user-supplied `mbti切图 2` PNGs are copied unchanged into `../report-art/`. The ENFJ image temporarily represents all 16 types; the four named panel illustrations now use their matching PNGs. See `../report-illustrations.json`.
