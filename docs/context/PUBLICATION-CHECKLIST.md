# M0 Evidence Publication Checklist

## Never collect or publish

- Passwords, API keys, access tokens, cookies, or inline authorization headers.
- `HF_TOKEN`, `NGC_API_KEY`, `DOCKER_AUTH_CONFIG`, cloud credentials.
- SSH private keys, known-host databases, complete SSH configuration, or Docker auth files.
- Complete environment dumps such as `env`, `printenv`, or `/proc/*/environ`.
- Private `*.private.md`, `.env.m0.local`, `artifacts/m0-private/`, or
  `deployments/bootstrap/out/` content, plus the local ignored `helper/` kit.
- Interrupted publisher `.*.staging.*` or `.*.previous.*` directories; staging
  may contain an unsanitized copy if a process was killed before cleanup.

## Private-only identifiers

- Real management/data IP addresses, subnets, gateways, and SSH endpoints.
- Physical hostnames, owner/site metadata, serial numbers, MAC addresses, RDMA
  node GUIDs, and compact GID/GUID fragments.
- Private usernames, home/repository/mount paths, registry prefixes, model IDs,
  and organization identifiers.

The tracked canonical document is `docs/environment/<name>.md`. A local
`docs/environment/<name>.private.md` companion must be ignored and absent from
the public commit/history. Private version control, if needed, belongs in a
separate private history.

## Evidence that should normally remain public

- Stable labels `spark-a` and `spark-b`.
- Interface names, PCI BDFs, NIC model, driver/firmware, link speed, and MTU.
- OS, kernel architecture, driver, CUDA, PyTorch, vLLM, NCCL, and MPI versions.
- Public image repositories, immutable digests, commands after redaction,
  test parameters, exit codes, timestamps, durations, and checksums.
- Throughput, latency, NIC deltas, collective results, known limitations, and
  clearly scoped failures/caveats.

## Generate and verify

```bash
scripts/m0/m0-evidence.sh publish 20260805-m0-final
# Review and check every item in the generated PUBLICATION-CHECKLIST.md.
scripts/m0/m0-evidence.sh verify-public 20260805-m0-final
```

The publisher must validate private manifests, stage instead of overwriting a
known-good export, reject traversal/symlink/special/binary/credential inputs,
remain inside the two dedicated evidence roots, sanitize identifiers, and pass
privacy, secret, working-tree, and staged-index gates before sealing the public
SHA256 manifest. `verify-public` is read-only and must work in a public clone
without `.env.m0.local`. Its generated checklist covers the evidence/repository
review; commit metadata, the push operation, and fresh-clone validation remain
the explicit outer release steps below.

## Before the squashed public commit

- [ ] Stage the intended public source tree (or prepare the squashed candidate)
  so both the working tree and Git index pass `repo-publication-scan.txt`.
- [ ] Review `publication-scan.txt`, `privacy-scan.txt`, and
  `repo-publication-scan.txt`; scanners do not replace manual review.
- [ ] Search manually for all capture-node usernames, hostnames, IP ranges,
  registry/model identifiers, private paths, owner/site metadata, and serials.
- [ ] Confirm no command contains an inline token/password.
- [ ] Confirm `git ls-files` contains no `*.private.md`, `.env.m0.local`,
  `artifacts/m0-private/`, `deployments/bootstrap/out/`, `helper/`, or publisher
  staging/backup path.
- [ ] Confirm no tracked binary remains; generated executables are untracked and ignored.
- [ ] Confirm sanitized files preserve versions, parameters, exit codes,
  benchmark values, limitations, and immutable digests.
- [ ] Confirm every generated manual-checklist item is checked and
  `verify-public` passes without changing the public tree.
- [ ] Review author/committer names and email addresses in the squashed tip and
  confirm the destination remote URL contains no embedded credentials.
- [ ] Create the public remote from the reviewed squashed commit only.
- [ ] Push one explicit reviewed branch/tip. Do not use `--mirror` or push old
  branches, tags, or other refs containing removed legacy/private evidence.
- [ ] Perform a final fresh-clone scan from the public remote before announcing it.
