# Publication Checklist

- [x] No `.env.m0.local`, credentials, tokens, SSH keys, or Docker auth files are present.
- [x] No tracked private/local content or interrupted publisher staging/backup directory is present.
- [x] No binary file is present in the evidence export or tracked repository.
- [x] Hostnames/FQDNs are replaced with stable labels such as `spark-a` and `spark-b`.
- [x] Management/data IP addresses, subnets, gateways, and SSH endpoints are redacted.
- [x] MAC addresses are redacted.
- [x] RDMA node GUIDs and compact NCCL GID/GUID fragments are redacted.
- [x] Usernames and private home/mount paths are redacted.
- [x] Private registry, model repository, and organization names are redacted where required.
- [x] Command lines do not contain inline tokens or passwords.
- [x] Image digests, driver/CUDA versions, interface names, test parameters, exit codes, and benchmark values remain intact.
- [x] No retained failure is relabeled as success; any deliberately excluded run is documented.
- [x] `publication-scan.txt` has been reviewed manually even when it reports PASS.
- [x] `privacy-scan.txt` and `repo-publication-scan.txt` have been reviewed manually.
