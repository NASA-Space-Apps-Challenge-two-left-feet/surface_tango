# Status: data

_Last update: 2026-11-15 (UTC−5)_

- Doing: verify the offline pitch image against the staged La Mojana cache (#37).
- Done: the Docker image now includes the report parser, reports, validation, config, and gate catalog; offline Compose skips cloud prewarming and requires the staged La Mojana manifest.
- Blocked: Docker is not installed on this Windows host, so the Compose walkthrough must run on a Docker host before claiming end-to-end acceptance.
