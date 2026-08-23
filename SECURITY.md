# Security Policy

## Supported Releases

Security fixes are provided for the current KythOS stable channel (`latest`).
The `testing` channel is a development preview and may contain incomplete or
unstable changes.

## Reporting A Vulnerability

Please do not open a public issue for a suspected vulnerability.

Use GitHub's private vulnerability reporting form:

https://github.com/kyth-os/kyth/security/advisories/new

Include the affected KythOS image or ISO version, reproduction steps, expected
impact, and any proof-of-concept material that is safe to share privately. Do
not include credentials, personal data, or unrelated system information.

We aim to acknowledge reports within seven days. Confirmed vulnerabilities are
triaged according to severity, affected release channels, and whether a fix or
upstream mitigation is available. We will coordinate disclosure timing with the
reporter and publish an advisory when users need to take action.

## Response Process

1. Acknowledge the report within seven days.
2. Reproduce or otherwise validate the issue when enough information is
   available.
3. Determine affected channels, severity, exploitability, and whether the issue
   is in KythOS code, release automation, packaging, or an upstream component.
4. Prepare a fix, mitigation, or upstream tracking note.
5. Publish a GitHub security advisory when users need to update, rotate
   credentials, avoid a feature, or take another action.

If a report affects an upstream project more than KythOS itself, we may ask the
reporter to coordinate with that upstream while we track any KythOS mitigation.

## Reporter Credit

We credit vulnerability reporters in advisories and release notes unless they
request anonymity or credit would increase risk before disclosure. If there have
been no confirmed vulnerabilities in a release, release notes may omit this
section.

## Security Contacts

Use GitHub private vulnerability reporting for security issues:

https://github.com/kyth-os/kyth/security/advisories/new

For non-sensitive defects, use public GitHub issues.

## Scope

Good-faith research against systems and accounts you own is welcome. Avoid
privacy violations, service disruption, destructive testing, and accessing
data that does not belong to you.
