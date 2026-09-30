"""Attach an email domain to an organization.

This is the onboarding step that makes self-registration possible. An account can
only be created on a domain that is already here, because a librarian can only
manage the holdings of a library that is in the system -- so somebody has to put
the institution in first, and that is an administrative act rather than something
an email address can decide about itself.

The two populations need different evidence, and the difference is recorded
rather than assumed:

* An **academic** domain (`kku.edu.tr`, `ox.ac.uk`) carries its own proof: nobody
  is issued such an address without belonging. The method is recorded as
  `academic_domain`.
* A **corporate** domain proves nothing by itself -- anybody can register a
  domain -- so `--method` is required and should say how the claim was actually
  established: a DNS record, a message answered from a role address, a signed
  letter. "Verified" without the how is not auditable later.

Usage
-----
    docker compose exec -T api sh -c "cd /app/scripts && python register_domain.py \\
        --domain kku.edu.tr --organization 'Kirikkale Universitesi'"

    ... --domain yayinevi.com.tr --organization 'Ornek Yayinevi' --method dns_txt

    ... --list
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text

from app.email_domains import domain_of, is_institutional
from app.core.ids import uuid7


def list_domains(connection) -> None:
    rows = connection.execute(
        text(
            """
            select d.domain, o.name, t.slug, d.verified_at, d.verification_method
            from control.organization_domains d
            join control.organizations o on o.id = d.organization_id
            join control.tenants t on t.id = o.tenant_id
            order by d.domain
            """
        )
    ).fetchall()

    if not rows:
        print("Tanımlı alan adı yok.")
        return

    print(f"{len(rows)} alan adı:\n")
    for domain, org, slug, verified_at, method in rows:
        state = f"dogrulandi ({method})" if verified_at else "DOGRULANMADI"
        print(f"  {domain:32} {org:34} {slug:44} {state}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain")
    parser.add_argument("--organization", help="organization name")
    parser.add_argument("--tenant", help="tenant slug, to disambiguate")
    parser.add_argument(
        "--method",
        help="how the claim was established (required for corporate domains)",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="record the domain but leave it unverified",
    )
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    engine = create_engine(os.environ["DATABASE_URL"])

    with engine.begin() as connection:
        if args.list:
            list_domains(connection)
            return 0

        if not args.domain or not args.organization:
            parser.error("gerekli: --domain ve --organization (veya --list)")

        domain = domain_of("x@" + args.domain.strip().lower().lstrip("@"))

        if domain is None:
            print(f"Geçersiz alan adı: {args.domain}")
            return 1

        academic = is_institutional(domain)
        method = args.method

        if method is None:
            if academic:
                method = "academic_domain"
            else:
                print(
                    f"'{domain}' akademik bir alan adı değil, bu yüzden kendi "
                    "başına kanıt sayılmaz.\n"
                    "Kurumsal alan adları için --method ile doğrulama yöntemini "
                    "belirtin (örn. dns_txt, role_address, letter)."
                )
                return 1

        query = (
            "select o.id, o.name, t.slug "
            "from control.organizations o "
            "join control.tenants t on t.id = o.tenant_id "
            "where lower(o.name) = lower(:name)"
        )
        params = {"name": args.organization}

        if args.tenant:
            query += " and t.slug = :slug"
            params["slug"] = args.tenant

        matches = connection.execute(text(query), params).fetchall()

        if not matches:
            print(f"Kuruluş bulunamadı: {args.organization}")
            return 1

        if len(matches) > 1:
            print(f"'{args.organization}' birden fazla kuruluşla eşleşiyor:")
            for _, name, slug in matches:
                print(f"  {name} ({slug})")
            print("--tenant ile hangisini kastettiğinizi belirtin.")
            return 1

        organization_id, organization_name, tenant_slug = matches[0]

        existing = connection.execute(
            text(
                "select id, organization_id from control.organization_domains "
                "where domain = :domain"
            ),
            {"domain": domain},
        ).fetchone()

        if existing is not None:
            if str(existing[1]) == str(organization_id):
                connection.execute(
                    text(
                        "update control.organization_domains "
                        "set verified_at = coalesce(verified_at, now()), "
                        "verification_method = :method, updated_at = now() "
                        "where id = :id"
                    ),
                    {"method": method, "id": existing[0]},
                )
                print(f"Güncellendi: {domain} -> {organization_name}")
            else:
                print(
                    f"'{domain}' zaten başka bir kuruluşa tanımlı. "
                    "Önce mevcut tanımı kaldırın."
                )
                return 1
        else:
            connection.execute(
                text(
                    """
                    insert into control.organization_domains
                        (id, domain, organization_id, verified_at,
                         verification_method, created_at, updated_at)
                    values
                        (:id, :domain, :organization_id, :verified_at,
                         :method, now(), now())
                    """
                ),
                {
                    "id": uuid7(),
                    "domain": domain,
                    "organization_id": organization_id,
                    "verified_at": (
                        None if args.no_verify else datetime.now(timezone.utc)
                    ),
                    "method": method,
                },
            )
            print(f"Eklendi: {domain} -> {organization_name} ({tenant_slug})")

        print(f"  tür     : {'akademik' if academic else 'kurumsal'}")
        print(f"  yöntem  : {method}")
        print(f"  durum   : {'doğrulanmadı' if args.no_verify else 'doğrulandı'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
