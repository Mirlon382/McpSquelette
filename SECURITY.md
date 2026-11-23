# Security policy

## Reporting a vulnerability

Open a [private security advisory](https://github.com/Mirlon382/McpSquelette/security/advisories/new)
rather than a public issue. Expect an answer within a week.

## What this skeleton does and does not protect

It is a starting point for your own server, so the honest list matters more than a badge.

- **No authentication ships with it.** An HTTP deployment serves whoever can reach the port. Put it
  behind a gateway, a VPN or your platform's auth proxy, or add a FastMCP auth provider before you
  expose it. `stdio` has no network surface at all.
- **`ALLOWED_HOSTS` defaults to `["*"]`** and logs a warning at startup: it accepts any `Host`
  header. Set the real hostname before publishing.
- **Rate limiting is per process and in memory.** Two replicas allow twice the traffic and a restart
  resets the counters.
- **`mask_error_details=True` is deliberate.** Only `AppToolError` text is public, so never put a
  token, an internal URL or a stack trace in a tool's error message.
- **The example note store is in memory.** It is a demonstration, not storage: it is lost on
  restart and shared by every caller of the process.

## Scope

Vulnerabilities in the skeleton's own code (middleware order, host/origin protection, the error
contract, the container image) are in scope. A weakness in *your* tool logic, or in a third-party
API it calls, is not.
