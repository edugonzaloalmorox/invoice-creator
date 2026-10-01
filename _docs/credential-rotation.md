# Credential rotation and incident procedure

This procedure uses placeholders and synthetic evidence only. Owners must replace
role names with the deployment team's approved contacts without adding credentials,
bank details, invoice contents, or production identifiers.

## Roles

- Secret owner: `ROLE_SECRET_OWNER`
- Service owner: `ROLE_SERVICE_OWNER`
- Security escalation: `ROLE_SECURITY_ESCALATION`
- Communications/notification owner: `ROLE_INCIDENT_COMMS`

## Issuance and storage

1. Create a dedicated service identity for the invoice backend.
2. Grant only the approved Drive/Docs scopes and access to the configured disposable
   or production template according to #TASK-8.
3. Store the key or workload-identity configuration in the deployment secret
   manager under a reference such as `secret-manager://invoice/google`.
4. Give runtime access to the backend identity only; do not write secret material
   to source control, images, local `.env` files, logs, tests, or tickets.
5. Record the secret reference, owner, issue date, and expiry metadata—not the value.

## Rotation

1. The secret owner creates a replacement credential in the secret manager.
2. Grant the replacement the same least-privilege access and test it against a
   disposable fixture/template.
3. Update the secret reference version atomically; do not print the value.
4. Restart or reload the backend through the deployment mechanism.
5. Verify `/api/health`, `/api/ready`, a sanitized template read, and a fixture
   generation/cleanup workflow.
6. Revoke the old credential only after the checks pass.
7. Record timestamps, version labels, status, and request IDs only.

## Revocation and emergency disablement

For suspected exposure, `ROLE_SECRET_OWNER` immediately revokes the credential and
`ROLE_SERVICE_OWNER` disables generation at the reverse proxy. Keep liveness and
safe readiness diagnostics available where possible. Preserve only redacted request
IDs and event timestamps. Never preserve raw provider payloads, tokens, PDFs,
document IDs, bank data, or request bodies.

## Incident lifecycle

1. Contain: disable generation, revoke the suspected credential, and restrict
   provider access.
2. Preserve evidence: save sanitized status, timestamps, deployment version,
   provider operation class, and request IDs in the approved incident system.
3. Assess scope: inspect access logs and secret-manager audit events without copying
   sensitive values.
4. Notify: `ROLE_SECURITY_ESCALATION` and `ROLE_INCIDENT_COMMS` determine required
   internal/customer/regulatory notifications.
5. Recover: issue a replacement, verify least privilege, restore traffic gradually,
   and check cleanup plus readiness.
6. Close: record root cause, remediation owner, retest evidence, and rotation date.

## Tabletop record

Scenario: synthetic credential reference is suspected to be exposed.  
Evidence date: 2026-10-01.  
Result: procedure executable in a credential-free environment; no real secret or
invoice data used.  
Open owner action: `ROLE_SERVICE_OWNER` must validate the secret-manager-specific
reload and audit-log commands under #TASK-21 before production use.
