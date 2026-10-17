# JRG's House of IPs safety checker

Automated, $0 safety check for https://jrghouseofip.com and https://www.jrghouseofip.com.
No secrets, no dependencies (Python standard library only). The site itself is deployed separately.

**Schedule:** every 2 hours at :23 (quick). The 14:23 UTC run is the daily full run (adds outbound links).
Manual run: Actions → JRG safety check → Run workflow.

**Quick checks:** all sitemap pages + home, /music/, /publishing/, /audiobooks/ and a release page return 200 (apex and www);
maintenance banner present; content guard (no "Summeer Fox", "James R. Gibson", "houseofips.com", "jrg@houseofips.com");
404 page works; SSL valid and more than 14 days from expiry; CSP, HSTS, X-Content-Type-Options, X-Frame-Options and
Referrer-Policy present (CSP must still allow Spotify); HTTP redirects to HTTPS; Google Safe Browsing (keyless transparency-report lookup).

**Daily full check:** every outbound link (Books2Read, Spotify, HyperFollow/DistroKid, YouTube, Smashwords, Booktopia, Deezer...),
Spotify embeds and external cover images: broken links fail, redirects to a different domain or parked/for-sale pages fail
as possible hijacks. Links behind bot protection (DistroKid's Cloudflare challenge) are listed as warnings, not failures.

**On failure** the run fails (GitHub emails the repo owner) and the run summary lists exactly what broke.
