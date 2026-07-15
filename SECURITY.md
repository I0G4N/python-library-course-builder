# Security policy

## Supported versions

Security fixes are applied to the latest released version and the default branch. Reports should identify the affected plugin version, generated-course version if relevant, and the smallest reproducible case.

## Report a vulnerability

Use GitHub Private Vulnerability Reporting for security-sensitive findings. Do not publish exploit details, access tokens, API keys, personal data, or private course material in an Issue or pull request. Ordinary correctness bugs that do not expose data or cross a trust boundary may be reported through GitHub Issues.

## Trusted-code boundary

The generated Runner, CLI, verifier, and pytest processes execute local Python. They are designed for code owned or reviewed by the learner and course author. They are not a hostile-code sandbox and do not provide container, virtual-machine, kernel, or user-account isolation.

- Keep the Runner bound to loopback.
- Do not expose it as a public grading service.
- Do not run untrusted submissions under an account that holds sensitive credentials.
- Use a separately hardened, disposable sandbox when evaluating hostile code.

Process groups, temporary workspaces, bounded output, path checks, and environment filtering are defense in depth for a local learning workflow. They do not change the operating-system privileges of submitted code.

## Course artifact visibility

Generated projects are authoring repositories. Hidden tests are not secret when teacher artifacts are distributed: reference implementations and verified tests are separated from the learner workspace, but remain inspectable by anyone with access to the complete repository. Version 0.2.0 does not provide an automated learner-only export. The supported secrecy path is to keep the complete teacher/authoring repository private.

Never commit real credentials to a course specification, runnable example, fixture, verification report, or generated project.
