# Security policy

## Reporting a vulnerability

Please report a vulnerability in this SDK **privately**, through GitHub's private vulnerability
reporting: open the repository's **Security** tab and choose **Report a vulnerability**
(<https://github.com/cruworldwine/cru-api-python/security/advisories/new>).

Never report a vulnerability in a public issue, pull request or discussion, and never include a
real credential, token or customer data in a report: describe the problem and how to reproduce it
with made-up values.

We will acknowledge the report, keep you informed while we investigate, and credit you in the
advisory unless you would rather we did not. A vulnerability in the Cru Trading API itself, rather
than in this SDK, can be reported the same way and will be passed on to Cru's API team.

## Supported versions

Security fixes go into the latest minor release only. Upgrade to it to receive them.

| Version                | Supported |
| ---------------------- | --------- |
| Latest minor (0.1.x)   | Yes       |
| Anything older         | No        |

## What the SDK does to keep you safe

- It never follows redirects, so your credentials are never sent to another host.
- It never logs your client key or secret, access or refresh tokens, or request and response
  bodies, and they never appear in `repr()` of a client or in an error's message.
- A refresh token is spent once: concurrent refreshes are serialised.
- Releases are published from GitHub Actions by PyPI Trusted Publishing, with build provenance
  attestations you can verify, for example with
  `gh attestation verify <file> --repo cruworldwine/cru-api-python`.
