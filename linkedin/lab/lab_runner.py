"""LinkedIn Lab Runner — CLI entrypoint.

Uso:
    python -m linkedin.lab.lab_runner --flow fingerprint
    python -m linkedin.lab.lab_runner --flow login
    python -m linkedin.lab.lab_runner --flow login --manual-password
    python -m linkedin.lab.lab_runner --flow viewer --search "designer cuiaba"
    python -m linkedin.lab.lab_runner --flow viewer --search "marketing" --profile-index 2

Flags:
    --flow {fingerprint|login|viewer}    Qual flow rodar (obrigatorio)
    --search TERM                        Termo de busca (viewer flow)
    --profile-index N                    Indice do profile (default 0 = primeiro)
    --manual-password                    Pausa pra digitar senha manual (login)
    --sites s1,s2                        Subset de sites fingerprint (default todos)
    --account-email EMAIL                Sobrescreve LINKEDIN_LAB_EMAIL do env
    --profile-name NAME                  Nome do user_data_dir (default 'lab_default')
    --headful                            Ja default em lab; flag explicita
"""
from __future__ import annotations
import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

# Garante que rodando como modulo
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from linkedin.lab import lab_runner  # noqa
else:
    pass

from linkedin.lab._event_emit import emit, mask_email  # noqa: E402


def build_lab_config(account_email: str, profile_name: str):
    """Builda LinkedInConfig isolada pra lab (user_data_dir lab_*)."""
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")

    from linkedin.config import LinkedInConfig, PROFILE_DIR, SESSION_DIR

    email = account_email or os.environ.get("LINKEDIN_LAB_EMAIL", "")
    if not email:
        raise SystemExit("LINKEDIN_LAB_EMAIL nao definido no .env e --account-email nao passado")

    safe = email.replace("@", "_at_").replace(".", "_") + "_" + profile_name
    user_data_dir = str(PROFILE_DIR / f"lab_{safe}")
    session_file = str(SESSION_DIR / f"lab_{safe}.json")

    # Proxy do env (ex: socks5://127.0.0.1:55081 = reverse tunnel PC residencial)
    proxy_server = os.environ.get("LINKEDIN_PROXY", "").strip() or None
    proxy_user = os.environ.get("LINKEDIN_PROXY_USER", "").strip() or None
    proxy_pass = os.environ.get("LINKEDIN_PROXY_PASS", "").strip() or None

    config = LinkedInConfig(
        account_email=email,
        account_type=os.environ.get("LINKEDIN_LAB_ACCOUNT_TYPE", "free"),
        proxy_server=proxy_server,
        proxy_username=proxy_user,
        proxy_password=proxy_pass,
        # Headful em lab (xvfb-run na VM Linux headless)
        headless=False,
        use_system_chrome=True,
        user_data_dir=user_data_dir,
        session_file=session_file,
        # Cuiaba defaults ja em config
    )
    return config


async def main_async(args):
    config = build_lab_config(args.account_email, args.profile_name)
    print(f"[lab] account={config.account_email}")
    print(f"[lab] user_data_dir={config.user_data_dir}")
    print(f"[lab] proxy={config.proxy_server or 'NONE (residential IP nativo)'}")
    print()

    emit(
        "run_started",
        flow=args.flow,
        account_email_masked=mask_email(config.account_email),
        profile_name=args.profile_name,
        run_id=os.environ.get("HERMES_LAB_RUN_ID", ""),
    )

    t0 = time.time()
    try:
        if args.flow == "fingerprint":
            from linkedin.lab.flows import fingerprint_baseline
            sites = args.sites.split(",") if args.sites else None
            result = await fingerprint_baseline.run(config, sites=sites)
        elif args.flow == "login":
            from linkedin.lab.flows import login
            result = await login.run(config, manual_password=args.manual_password)
        elif args.flow == "viewer":
            from linkedin.lab.flows import viewer_test
            result = await viewer_test.run(config, search_term=args.search, profile_index=args.profile_index)
        else:
            raise SystemExit(f"flow invalido: {args.flow}")
    except Exception as e:
        emit(
            "run_failed",
            flow=args.flow,
            error=f"{type(e).__name__}: {str(e)[:500]}",
            duration_ms=int((time.time() - t0) * 1000),
        )
        raise

    duration_ms = int((time.time() - t0) * 1000)
    print()
    print("=" * 70)
    print(f"[lab] FLOW {args.flow.upper()} COMPLETO")
    print("=" * 70)
    emit(
        "run_completed",
        flow=args.flow,
        duration_ms=duration_ms,
        status="success",
        summary=str(result)[:200] if result else "",
    )
    return result


def main():
    parser = argparse.ArgumentParser(description="LinkedIn Lab Runner")
    parser.add_argument("--flow", required=True, choices=["fingerprint", "login", "viewer"])
    parser.add_argument("--search", default="designer", help="Termo de busca (viewer)")
    parser.add_argument("--profile-index", type=int, default=0)
    parser.add_argument("--manual-password", action="store_true")
    parser.add_argument("--sites", default="", help="Subset csv pra fingerprint flow")
    parser.add_argument("--account-email", default="", help="Override LINKEDIN_LAB_EMAIL")
    parser.add_argument("--profile-name", default="default", help="Sufixo user_data_dir")
    parser.add_argument("--headful", action="store_true", help="Headful (ja default)")
    args = parser.parse_args()

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\n[lab] interrompido")
        emit("run_failed", flow=args.flow, error="interrupted_by_user")
        sys.exit(130)


if __name__ == "__main__":
    main()
