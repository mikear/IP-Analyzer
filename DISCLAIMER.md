# Disclaimer

IP Analyzer is intended for **authorized** security and forensic work: incident response, OSINT investigations with a lawful basis, and legal reports where you control the evidence.

- Geolocation and ISP data come from [ipinfo.io](https://ipinfo.io). Accuracy is not guaranteed; records can be stale or misattributed. Do not present enrichment as sole proof of identity.
- The deterministic parser reads IPv4/IPv6 and timestamps from `.txt`, `.log`, `.csv` and `.docx` files you provide. It never uploads case data — enrichment requests go to ipinfo.io only when you run an analysis with a token.
- Timestamps in `DD/MM/YYYY` are interpreted day-first, per the default report format. Ambiguous dates log a warning; verify manually for legal use.
- The SHA256 in every report covers the input file as received, to preserve chain of custody. Keep the original file and the report together.
