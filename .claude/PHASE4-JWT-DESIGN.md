# Phase 4 Per-MCP JWT — Design Decision (B11 root-cause)

**Sealed**: 2026-06-20
**Method**: 4-approach adversarial design panel (4 research reports + 4 designs + 16 multi-lens judge verdicts: security / complexity / migration-risk / cobaia-fit)
**Status**: APPROVED FOR IMPLEMENTATION (Opus 4.7 parallel session)

---

## 1. Decision

### WINNER: **Approach C — Hybrid JWT Audience (primary) + Access Matrix (defense-in-depth)**, built on **Approach B's offline static-mint substrate** for v1 (no live `/oauth/token` endpoint).

This is a **deliberate fusion**: take **C's additive Branch-0 architecture and dual-layer enforcement model** (the lowest-migration-risk shape) and implement issuance via **B's offline-mint script with the private key OFF the VM** (the cobaia-right, lowest-attack-surface mint path). We do NOT build a live in-process Authorization Server in v1.

### Aggregate score table (4 approaches × 4 lenses, 1-10)

| Approach | Security | Complexity | Migration-risk | Cobaia-fit | **Mean** |
|---|---|---|---|---|---|
| A — Gateway-as-IdP (live `/oauth/token`) | 7 | 5 | 7 | 4 | **5.75** |
| **B — Static offline-mint JWT (env-stored)** | 6 | 7 | **8** | 7 | **7.00** |
| **C — Hybrid JWT aud + access_matrix DiD** | 7 | 6* | 7* | 7* | **6.75** |
| D — mTLS + JWT (D-minus = JWT only) | — | — | — | — | (mTLS rejected; JWT subset folds into B/C) |

\* C's complexity/migration/cobaia lenses were partially scored (judge transcript truncated). C's security lens (7) and verified-feasibility notes are complete. The fusion below adopts **C's enforcement design** (mean-competitive, lowest migration risk per judge) on **B's mint substrate** (highest migration-risk score 8, best cobaia time-to-value, private key never on VM) — taking the best-scoring axis from each.

**Effort**: B substrate ≈ 22h + C's Branch-0 wiring/tests ≈ 6h = **~26h total** across PHASE4-A/B/C.

### Why it wins

- **Security fix (B11 root-cause)**: The `aud` claim cryptographically binds each token to ONE MCP. A token minted `aud=hermes-linkedin` presented to `/dispatch/hermes-prospects/...` fails `InvalidAudienceError` at decode — a compromised caller CANNOT laterally reach MCPs outside its scope, regardless of the allowlist. This is the exact property shared-bearer + allowlist never had ("issuance without enforcement is partial control"). It also signs `sub` server-authoritatively, **killing the `fallback_spoofable` path** (today a shared-bearer holder claims any `requester` from the body).
- **Complexity fit (solo founder)**: No live AS. No `/token`, `/authorize`, PKCE, refresh, DCR, consent, JWKS-over-network. Issuance = one offline script (`gen_jwt_tokens.py`); validation = one new branch in an existing 40-line pure function (`derive_requester`). Static JWTs decode offline (jwt.io / pyjwt CLI) for debugging without touching the running gateway.
- **Migration safety**: 100% additive. New **Branch 0** (JWT) inserted BEFORE the untouched per-role (Branch 1) and shared-bearer (Branch 2) branches. JWT-shape detection (2-dot test) → dual-accept old+new simultaneously. Per-caller incremental flip, instant rollback (unset one env var → caller falls back to its retained opaque bearer). Reuses the **already-shipped R5-PHASE3 `HERMES_GATEWAY_STRICT_BEARER` kill-switch** (requester.py:71) for shared-bearer deprecation — no new kill-switch code.
- **Cobaia-fit**: Auth-credential-format change at the gateway layer ONLY. Zero touch to LinkedIn automation, schedulers, warmup, or any cobaia activation path. Private key never on the VM (aligns with GUARDRAILS PC=source / VM=runtime) → a VM compromise cannot MINT tokens, only steal existing ones. Deployable with cobaia paused OR running.

### What we explicitly DON'T do (rejected)

- **Approach A — Gateway-as-IdP (live `/oauth/token`)**: REJECTED for v1. Lowest cobaia-fit (4). Puts a NEW live runtime service on the single dispatch choke point (hot-path latency, mid-deploy crash risk, startup signing-key load = new global failure mode). Concentrates a forge-any-`aud` signing key IN the runtime VM process (issuer + enforcer in one binary). 34h for a marginal security gain over the static path. **The live-issuance/short-TTL upgrade is deferred to a future phase IF/WHEN a public/third-party MCP consumer appears (F.5.6).**
- **Approach D — mTLS transport layer**: REJECTED (over-engineered, judges concur). Gateway is loopback-only (`127.0.0.1:55401`); MCPs are local stdio subprocesses (no network hop); PC↔VM already rides an authenticated SSH reverse tunnel (mutual auth + AEAD). mTLS = double-encryption with zero added threat coverage + a new cert-expiry outage class. **Keep loopback-only + SSH as the transport security; take only D's JWT subset (which == B/C).**
- **HS256 / any shared HMAC secret**: REJECTED across all designs. A shared secret on the VM lets a VM compromise MINT tokens for every MCP, defeating per-target isolation. **EdDSA asymmetric only.**
- **python-jose**: REJECTED. Unpatched CVE-2024-33663 (alg-confusion) + CVE-2024-33664 (JWT-bomb DoS), effectively unmaintained. **PyJWT >=2.13.0 only.**
- **Removing access_matrix**: REJECTED. Kept permanently as Layer 2 (catches issuer misconfig — a wrong-`aud` token is still policy-blocked; single human-readable policy/audit source; covers residual non-JWT callers during migration).

---

## 2. Target Architecture

### Token format (RFC 9068 `at+jwt` profile, RFC 8707 single-resource aud)

**Header**: `{ "alg": "EdDSA", "typ": "at+jwt", "kid": "<key-id>" }`

**Claims**:
| Claim | Value | Source |
|---|---|---|
| `iss` | `"hermes-gateway"` | fixed |
| `sub` | requester id, e.g. `"brain-f5"` | **signed, server-authoritative** (replaces per_role_map lookup; kills body-spoof) |
| `aud` | single MCP id, e.g. `"hermes-linkedin"` | **per-MCP cryptographic gate** (RFC 8707 one-resource) |
| `exp` | mint + TTL | TTL = **90 days** (static, no live issuer — see §5 owner decision) |
| `nbf` | mint time | |
| `iat` | mint time | |
| `jti` | uuid4 | logged for audit; enables future denylist revocation |
| `scope` | empty in v1 (`""`) | reserved for future tool-level granularity; access_matrix gates v1 |

> **aud convention**: use the **bare MCP id** (`hermes-linkedin`), NOT a URI. Rationale: the dispatch path param is the bare `server_name` (`/dispatch/{server}/{tool}`), so `audience=server_name` is a direct string match with zero canonicalization layer to drift. (A `canonical_uri()` map was in C's design; we drop it as needless complexity for a single-owner box — fewer moving parts to keep in sync with access_matrix.)

### Algorithm & key management

- **Algorithm**: **EdDSA / Ed25519** (fastest, deterministic, no weak-RNG, asymmetric → validators hold public key only). RS256 selectable via config only if a future HSM/compat need arises.
- **Library**: **PyJWT >=2.13.0** + `cryptography` extra (native `audience=` in `decode()`, native EdDSA, cleanest CVE posture, pinned >=2.13.0 for the JKU/SSRF fix). FastMCP's `JWTVerifier` NOT used in v1 (validation is at the gateway dispatch layer, the single resource-server front for all stdio MCPs — not inside each subprocess).
- **Private key**: Ed25519 private key generated **on the PC** (owner workstation = source-of-truth per GUARDRAILS), stored at `D:/dev-projects/main/hermes-cloud-studio/.keys/jwt_ed25519_<kid>.pem`, **gitignored, NEVER deployed to VM**.
- **Public key**: deployed to VM at `mcps/gateway/keys/jwt_pub_<kid>.pem` (committable). Loaded at `build_app()` startup. Multiple `kid` PEMs coexist on disk during rotation.
- **No JWKS endpoint in v1** (single static verifier loads pubkey from file). A local JWKS-from-file is a trivial extension if multiple kids must coexist long-term.

### Issuance (offline static script — NO live endpoint)

`mcps/gateway/scripts/gen_jwt_tokens.py` (run on PC by owner):
1. Read `access_matrix.json` as the authoritative `caller → allowed-MCP` map.
2. **Expand wildcards**: `"*"` rows (`brain-core`, `api`) resolve against the **live MCP inventory** — explicit list: `sentry, hermes-linkedin, hermes-prospects, hermes-skills, hermes-llm, hermes-hunter`. (Mis-expansion is a top risk — see §5. Script MUST fail loudly if a matrix MCP is not in the known inventory.)
3. Mint ONE Ed25519 JWT per `(caller, allowed-MCP)` pair with `sub=caller`, `aud=mcp`, signed with the PC private key.
4. Emit `.env` fragment: `HERMES_GATEWAY_JWT_<CALLER>_<MCP>=<jwt>` (uppercase, hyphens→underscores).

### Validation (dispatch flow — new Branch 0 in `derive_requester`)

`derive_requester()` gains a **`server_name` parameter** (currently absent; `dispatch_real` already has it in scope at the call site — pass it through. This is the ONLY signature change). New branch order:

```
Branch 0 (NEW, highest priority): JWT
  if bearer is JWT-shaped (2 dots):
    try jwt.decode(token, pubkey_for(kid),
        algorithms=["EdDSA"],          # alg allowlist; rejects "none"
        audience=server_name,          # ← aud MUST == target MCP, else InvalidAudienceError
        issuer="hermes-gateway",
        leeway=30,                     # <=30s clock skew
        options={"require": ["exp","iat","nbf","aud","iss","sub"]})
    assert header["typ"] in ("at+jwt","application/at+jwt")   # reject ID-token confusion
    on success → return (claims["sub"], "trusted_jwt")
    on aud mismatch  → return (None, "denied_aud_mismatch")
    on expired/bad   → return (None, "denied_jwt_invalid")
Branch 1 (UNCHANGED): per-role bearer  (requester.py:67-68)
Branch 2 (UNCHANGED): shared bearer    (requester.py:70-79, still strict-gated)
```

### Two-layer enforcement (defense-in-depth)

1. **Layer 1 (PRIMARY, cryptographic)**: JWT signature valid + `aud == server_name`. Contains lateral movement.
2. **Layer 2 (UNCHANGED, policy)**: `access_matrix.check(sub, server_name)` runs EXACTLY as today (server.py:380) on the JWT-derived `sub`. Redundant-by-design for JWT callers — kept as backstop against issuer misconfig + single audit/policy source + covers non-JWT callers mid-migration.

### How it replaces shared bearer + what happens to access_matrix

- **Shared bearer**: deprecated via the existing `HERMES_GATEWAY_STRICT_BEARER=true` switch once all callers emit JWTs (PHASE4-C). Shared bearer then returns `denied_strict`.
- **Per-role bearers**: retained as the fallback floor throughout; optionally removed only after JWT proven stable (kept in code for emergency rollback).
- **access_matrix**: **KEPT PERMANENTLY** as Layer 2 + as the input to the mint script.

---

## 3. Migration Plan (zero-downtime from current R5 state)

### Dual-accept window
JWT-shape (2-dot) detection makes Branch 0 a no-op for opaque bearers. Old per-role bearers AND new JWTs are BOTH valid for the entire window. Callers flip independently; the per-role bearer floor is never deleted until PHASE4-C.

### Phased rollout

| Phase | What | Behavior change | Reversible by |
|---|---|---|---|
| **PHASE4-A** | Infra: keygen (PC) + pubkey deploy (VM) + `gen_jwt_tokens.py` + Branch 0 in `derive_requester` + `server_name` param wiring + tests. All behind `HERMES_GATEWAY_JWT_ENABLED=false`. | **NONE** (flag off → Branch 0 never executes; gateway identical to today) | flag stays false |
| **PHASE4-B** | Flip `HERMES_GATEWAY_JWT_ENABLED=true`. Migrate callers ONE at a time, blast-radius ascending: **brain-f8 (sentry-only) → breadcrumb → brain-f4 → brain-core/f5/f6/f9 → brain-f7-cobaia* LAST**. Each caller keeps its per-role bearer as fallback. 7-day audit per tranche. | per-flipped-caller only | unset that caller's JWT env var (instant fallback) OR flag=false (global) |
| **PHASE4-C** | After 7d zero `R5_FALLBACK` + zero legacy-bearer use: set `HERMES_GATEWAY_STRICT_BEARER=true` (reuse R5-PHASE3 switch). Optionally remove per-role bearer env. | shared bearer → `denied_strict` | set STRICT_BEARER=false; per-role bearers still in env |

### Rollback strategy per phase
- **PHASE4-A**: nothing to roll back (dormant).
- **PHASE4-B**: per-caller `unset HERMES_GATEWAY_JWT_<CALLER>_<MCP>` → that caller reverts to opaque per-role bearer with zero gateway change. Global: `HERMES_GATEWAY_JWT_ENABLED=false`.
- **PHASE4-C**: `HERMES_GATEWAY_STRICT_BEARER=false` re-opens shared bearer; per-role bearers never removed until the very end → system degrades to exactly today's R5 posture.

### Cobaia-safety gates
- `brain-f7-cobaia` + `brain-f7-cobaia-autotune` are migrated **LAST** (after all other callers prove clean for 7d). They never depend on a half-migrated state.
- Dual-accept guarantees an un-migrated/reverted cobaia caller keeps its opaque bearer working.
- All failures fail **CLOSED** (401/403) — never open, never silent escalation. Worst case = a flipped caller loses MCP access → revert one env var.
- **HARD GATE**: do NOT flip `STRICT_BEARER=true` (PHASE4-C) while cobaia is live-activating (~Day 14) unless 7d clean audit AND owner GO.

---

## 4. Implementation Phases

### PHASE4-A — Infra (issue + validate + dual-accept, dormant)
- **Scope**: keygen tooling, mint script, JWT validation Branch 0, `server_name` param threading, full test suite. Ships dormant behind `HERMES_GATEWAY_JWT_ENABLED=false`.
- **Files**:
  - NEW `mcps/gateway/scripts/gen_jwt_tokens.py` (offline mint, wildcard expansion, fail-loud on unknown MCP)
  - NEW `mcps/gateway/scripts/gen_ed25519_keypair.py` (one-shot keygen, PC-only)
  - EDIT `mcps/gateway/requester.py` (add Branch 0 + `server_name` param + pubkey loader + `try_validate_jwt` helper)
  - EDIT `mcps/gateway/server.py` (pass `server_name` to `derive_requester` at call site; load pubkey + `HERMES_GATEWAY_JWT_ENABLED` flag at `build_app()`; log `denied_aud_mismatch`/`denied_jwt_invalid`/`token_kind=jwt`+`jti`+`aud`)
  - NEW `mcps/gateway/keys/jwt_pub_<kid>.pem` (committed pubkey)
  - EDIT `.gitignore` (exclude `.keys/`)
  - NEW `tests/test_phase4_jwt.py`
  - EDIT existing R5 test fixtures calling `derive_requester` directly (add `server_name` arg)
  - EDIT `requirements*.txt` (PyJWT>=2.13.0 + cryptography)
- **Effort**: ~16h
- **Acceptance**: gateway behaves IDENTICALLY with flag off (all existing R5 tests green); with flag on + a hand-minted JWT, a correct-`aud` token dispatches (`trusted_jwt`), a wrong-`aud` token 403s (`denied_aud_mismatch`), an expired token 401s, a `none`-alg token rejected, an ID-token (`typ!=at+jwt`) rejected. `validate_implementation.py` gate stays >=20/22.
- **Cobaia-blocking?**: NO (dormant).
- **Model**: **Opus** (crypto validation correctness is the security boundary — subtle decode bugs become B11 bypasses).

### PHASE4-B — Migrate callers (dual-accept live)
- **Scope**: per-caller token-selection (pick JWT by target MCP via `os.getenv(f"HERMES_GATEWAY_JWT_{caller}_{server}")`, fall back to legacy bearer if unset). Flip `JWT_ENABLED=true`. Migrate blast-radius-ascending.
- **Files** (each keeps legacy bearer as fallback): `brain/dispatch.py`, `core/sentry_via_gateway.py`, `core/auto_skill_runner.py`, `api/observability.py`, `vm_api/mcp_coverage.py` (header path), `mcps/hermes-linkedin/server.py`, `mcps/hermes-prospects/server.py`.
- **Effort**: ~8h (incremental, per-caller)
- **Acceptance**: each migrated caller logs `trust_mode=trusted_jwt`; 7d zero `denied_aud_mismatch`/`denied_jwt_invalid` for that caller; access_matrix still allows each `sub` (no policy drift); cobaia callers migrated last and verified.
- **Cobaia-blocking?**: PARTIAL — cobaia callers are migrated in this phase but LAST; do not start cobaia-caller migration mid-activation without owner GO.
- **Model**: **Sonnet** (mechanical per-caller edits following an established pattern; Opus only if a caller has nonstandard dispatch).

### PHASE4-C — Kill old bearer (JWT-primary)
- **Scope**: `HERMES_GATEWAY_STRICT_BEARER=true` (reuse R5-PHASE3). Optionally remove per-role bearer env. access_matrix stays as Layer 2.
- **Files**: env/config only (+ optional cleanup in caller modules).
- **Effort**: ~2h
- **Acceptance**: shared bearer → `denied_strict`; 7d prior clean audit; rollback (`STRICT_BEARER=false`) verified.
- **Cobaia-blocking?**: YES — HARD GATE: requires 7d clean audit + owner GO + NOT during live cobaia activation.
- **Model**: **Sonnet** (config flip + verification).

---

## 5. Risks + Open Questions for Owner

### Top risks + mitigations
| Risk | Severity | Mitigation |
|---|---|---|
| **Private-key leak (god-key)** — one Ed25519 private key on PC mints any `(sub,aud)`. Net-new catastrophic mode (opaque bearers are unforgeable today). | HIGH | Key on PC ONLY (never VM), gitignored, 0600. `kid`-based rotation. Future: jti denylist + HSM. VM compromise alone cannot forge. |
| **90-day TTL + no native revocation** — leaked token replayable for full TTL. | MED-HIGH | `jti` logged for future denylist. Rotation (regen + redeploy + restart) is the v1 revocation. Owner decision below may shorten TTL. |
| **Wildcard mis-expansion** — `gen_jwt_tokens.py` must expand `"*"` (brain-core, api) correctly or under/over-provision. | MED | Script fails LOUD if a matrix MCP ∉ known inventory; explicit inventory list; unit-test expansion. |
| **Silent fallback drift** — `HERMES_GATEWAY_JWT_<CALLER>_<MCP>` name must match access_matrix or caller silently uses legacy bearer. | MED | 7d legacy-use audit per tranche; generator emits a manifest cross-checked against access_matrix; loud warn-log on every legacy-bearer use during PHASE4-B. |
| **Key-load failure bricks gateway** — wrong/missing pubkey or kid mismatch fails CLOSED at the single choke point. | MED | Dual-accept (legacy bearers unaffected until STRICT). Startup degrades to opaque-only if `JWT_ENABLED=false`. Test key-load path in CI before PHASE4-A merge. |
| **Clock skew** — Ed25519 exp/nbf with <=30s leeway. | LOW | VM clock sync (chrony/ntp) already standard; 90d TTL makes skew negligible. |

### Decisions owner MUST make before PHASE4-A
1. **Token TTL**: Plan defaults to **90 days** (static, no live issuer — matches infra-credential model). Shortening to e.g. 30 days increases rotation frequency but bounds leak window. → **Owner picks TTL.**
2. **Algorithm**: Plan defaults to **EdDSA/Ed25519**. Confirm (vs RS256 only if a specific HSM need exists). → **Confirm EdDSA.**
3. **Dual-accept duration**: 7-day clean audit per tranche before STRICT. Confirm 7d is acceptable vs cobaia Day-14 timeline (PHASE4-C may need to wait until after activation). → **Owner confirms gate timing.**
4. **jti denylist now or later?**: v1 ships WITHOUT live revocation (rotation = revocation). Build a denylist table now, or defer to a follow-up? → **Owner decides scope.**
5. **Key custody**: confirm `.keys/` on PC + gitignore + backup strategy (a lost private key = must regen all tokens). → **Owner confirms custody/backup.**

---

## 6. BLACKLIST R2 + Test Strategy

### BLACKLIST R2 — confirmed ZERO touch
This change is **gateway-auth-layer only**. It does NOT touch any anti-detection / behavioral subsystem:
- ❌ `linkedin/stealth.py` — untouched
- ❌ `linkedin/human.py` — untouched
- ❌ `linkedin/preflight*` — untouched
- ❌ `linkedin/cooldown.py` / limiter — untouched
- ❌ `ollama_router` — untouched
- ❌ LinkedIn automation, schedulers, warmup, cobaia activation path — untouched

The only behavioral effect is HOW `requester` is derived in `dispatch_real`; WHAT tools run is unchanged.

### Test plan (`tests/test_phase4_jwt.py`)
1. **Issuance**: `gen_jwt_tokens.py` produces a valid EdDSA JWT per `(caller,MCP)`; wildcard `"*"` expands to full inventory; fails loud on unknown MCP.
2. **Validation — happy path**: correct-`aud` JWT → `(sub, "trusted_jwt")`; `sub` from token, NOT body.
3. **aud-mismatch deny**: JWT `aud=hermes-linkedin` against `server_name=hermes-prospects` → `denied_aud_mismatch` → 403.
4. **expired deny**: `exp` in past → `denied_jwt_invalid` → 401.
5. **alg/typ confusion**: `alg=none` rejected; `typ!=at+jwt` (ID-token) rejected; HS256 token rejected.
6. **bad signature**: token signed by a different key → rejected.
7. **migration dual-accept**: with `JWT_ENABLED=true`, an opaque per-role bearer STILL resolves via Branch 1; a shared bearer STILL hits Branch 2 (strict-gated).
8. **dormant**: with `JWT_ENABLED=false`, Branch 0 never executes (all R5 tests green, byte-identical behavior).
9. **defense-in-depth**: a valid JWT whose `sub` is NOT allowed for `server_name` in access_matrix → still 403 (Layer 2 backstop).
10. **server_name param**: existing R5 fixtures updated; `derive_requester` signature change does not break Branch 1/2.
