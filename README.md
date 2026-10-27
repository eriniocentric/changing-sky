# Changing Sky

**🌌 Open the site: https://eriniocentric.github.io/changing-sky/**

*A community explorer of Vera C. Rubin Observatory alerts. Not an official Rubin Observatory product.*

An interactive sky map of public alerts from the NSF–DOE Vera C. Rubin Observatory (LSST), for education and discovery.

**Open it:** the page is served by GitHub Pages from `index.html`.

## What it shows
- 191,230 objects detected on the night of 2026-07-14 (UTC), the most recent night before Rubin went off-sky after the July 2026 winter storm.
- Alert types: supernovae and classified transients, unclassified TNS transients, AGN/quasars/blazars, variable stars, changes in known galaxies, extragalactic candidates, hostless transients, unidentified sources, and changes on catalogued stars.
- Background sky from public HiPS surveys via Aladin Lite (CDS): Rubin First Look, DSS2, DESI Legacy Surveys, DES, Pan-STARRS, 2MASS, WISE, GALEX, ROSAT, radio and gamma-ray surveys.
- Clicking an alert loads its science/template/difference cutouts and light curve live from the Fink broker API.

## Community
Sign in with an emailed link (no password) to **upvote** alerts that deserve a closer look, tag *why* (rising fast, no host galaxy, odd colour, unusual light curve, possible artefact…), and **comment**. The **Most wanted** tab ranks alerts by votes; voted alerts glow on the sky as *Community picks*. A moderator reviews the top alerts before anything is sent for follow-up (e.g. TNS reports, Las Cumbres Observatory education telescopes, AAVSO). Votes and comments are stored in Supabase with row-level security: anyone can read, only signed-in users can write, one vote per person per alert.

## Data sources and method
- Alerts: Fink broker public API (science streams, catalogue classes, and cone searches over the night's fields), ~94% of the objects Fink recorded that night.
- Classification: Fink cross-matches (TNS, VSX, blazar catalogues, HyperLEDA) plus a 1-arcsecond cross-match against SIMBAD, Gaia DR3 and Milliquas via the CDS XMatch service.
- Quality cuts: subtraction dipoles, glint trails, saturated cores and SNR < 5 removed; unidentified detections require Rubin reliability ≥ 0.8.

## Caveats
- Gaia quasar *candidates* (most of the AGN class) include some misclassified variable stars.
- Solar System (asteroid) alerts are not included.
- Requires an internet connection (Aladin Lite, survey images and alert data are loaded from CDS and Fink).

Rubin alert data are world-public. Acknowledge: NSF–DOE Vera C. Rubin Observatory; Fink broker; CDS Strasbourg (Aladin Lite, SIMBAD, XMatch); ESA Gaia.
