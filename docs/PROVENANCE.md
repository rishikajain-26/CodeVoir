# CodeVoir Provenance

This repository includes a tamper-evident provenance fingerprint. The repository does **not** store the private proof phrase in plain text.

Fingerprint:

```txt
sha256:ec5d49bf469257667e3dc054623b351ac01761c868da49937fc4160f220ea1ff
```

To verify ownership later, the original author can reveal the exact private proof phrase and run:

```bash
python scripts/verify_provenance.py
```

The verifier will hash the entered phrase and compare it with the stored fingerprint.
