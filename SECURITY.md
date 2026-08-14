# Security

NCA Toolkit exposes powerful media-processing endpoints and also includes a remote Python execution endpoint. Treat the API as a privileged service, not a public unauthenticated utility.

- Always use a long random `API_KEY`; the Railway template should generate it automatically.
- Never publish the API key in screenshots, logs, workflow exports, or client-side code.
- Rotate the key immediately if it is exposed.
- Keep the service at one replica unless you understand the upstream in-process queue/job-status model.
- Returned Railway Bucket URLs are presigned and time-limited; anyone who receives one can access that object until it expires.

For vulnerabilities in the upstream application, report them to the upstream No-Code Architects Toolkit project. For issues introduced by this Railway wrapper, open a private security report on this repository once GitHub Security Advisories are enabled.
