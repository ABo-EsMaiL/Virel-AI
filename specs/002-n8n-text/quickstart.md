# Stage 002 verification

1. Keep n8n running; close the old gateway/browser using its profile.
2. Set private gateway .env to the existing profile/key; one worker listens on the host interface reachable by Docker.
3. Use an ordinary OpenAI credential with Base URL http://host.docker.internal:8001/v1.
4. Execute native OpenAI Chat Completion (1.8) and Model Response text (2.3), raw/simplified. No Code/HTTP replacement node.
5. Check known output, structured failures and observed/unavailable usage. Record native node version/model/result separately.

Offline command: python -m unittest discover -s tests -v. Live fixtures/evidence are supplied as implementation proceeds; this is not an assertion they have passed yet.
