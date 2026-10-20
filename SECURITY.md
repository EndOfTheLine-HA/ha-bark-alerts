# Privacy and safety reports

Never attach learned RF codes, Home Assistant config entries, backups, service
traces, home audio/video, private addresses, or household camera maps to a public
issue. Codes can control a physical receiver and must be treated as private.

Report vulnerabilities and any unexpected RF send privately to the repository
maintainer before public disclosure. No transmissions are allowed during setup;
automatic sends require explicit arming and disabling dry run. The manual test
button is explicitly labelled as a physical send and bypasses those two toggles.

Only beep commands are in scope. The integration cannot verify the physical
meaning of arbitrary RF payloads; test off the animal. Third-party service logs
can expose payloads even when this integration's diagnostics do not.
