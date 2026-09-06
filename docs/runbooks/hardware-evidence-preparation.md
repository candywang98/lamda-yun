# Hardware evidence preparation

`scripts/prepare-hardware-evidence.py` is an offline evidence assembler for P2-011 and P3-012. It never opens a device connection, invokes LAMDA, or submits to an external platform.

## Safe default

Running the command without input files prints the authorization and run-result contracts. It does not write a file and always reports `hardwareEvidence=false`.

```bash
.venv/bin/python scripts/prepare-hardware-evidence.py --task-id P2-011
.venv/bin/python scripts/prepare-hardware-evidence.py --task-id P3-012
```

Use the task evidence templates as the starting point:

- `artifacts/tasks/P2-011/device-evidence/authorization-template.json`
- `artifacts/tasks/P2-011/device-evidence/run-result-template.json`
- `artifacts/tasks/P3-012/device-evidence/authorization-template.json`
- `artifacts/tasks/P3-012/device-evidence/run-result-template.json`

## Preview

The preview reads existing evidence files and computes their hashes, but writes nothing and does not claim hardware acceptance:

```bash
.venv/bin/python scripts/prepare-hardware-evidence.py \
  --task-id P2-011 \
  --authorization /authorized-input/authorization.json \
  --run-result /authorized-input/run-result.json \
  --evidence-root /authorized-input/device-evidence
```

## Explicit write and final gate

Only after an authorized external runner has produced physical-device evidence may an operator request a write. The output must be directly inside the evidence root. The assembler hashes the referenced files, writes the bundle, and immediately calls `scripts/validate-hardware-evidence.py`. A failed gate removes the bundle.

```bash
.venv/bin/python scripts/prepare-hardware-evidence.py \
  --task-id P3-012 \
  --authorization /authorized-input/authorization.json \
  --run-result /authorized-input/run-result.json \
  --evidence-root /authorized-input/device-evidence \
  --output /authorized-input/device-evidence/bundle.json \
  --write \
  --attest-physical-device
```

The command rejects Mock and simulator sources. P2-011 accepts only the required read-only actions. P3-012 requires authorized-account metadata, PREPARE, single-shot COMMIT, RECONCILE, and a durable commit intent. The CLI does not make either task accepted by itself; real authorized hardware evidence is still mandatory.
