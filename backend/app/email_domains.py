"""Which addresses may become accounts, and what kind of account they get.

Two populations, two rules
--------------------------
An **institutional** address (a university or library on `.edu`, `.edu.tr`,
`.ac.uk`, ...) is its own proof of affiliation: nobody is issued an
`@kku.edu.tr` address without belonging to the institution. So the address only
has to be shown to receive mail, and the account is a librarian/academic one.

A **corporate** address carries no such guarantee. A publisher's
`@yayinevi.com.tr` proves nothing by itself -- anyone can register a domain --
so the domain has to be claimed for an organization and verified before an
account on it is accepted. That is the "kurumsal mail adres doğrulaması" the
brief asks for.

Free mail providers are refused outright
----------------------------------------
`@gmail.com` is neither institutional nor corporate. It cannot demonstrate
affiliation, and tying it to an organization would let one person's private
mailbox speak for a company. Refusing them is the entire point of asking for a
work address, so this is a refusal and not a weaker kind of account.

This is the *first* gate, not the only one. Passing it means "this address could
belong to somebody at such an organization"; the verification step and the
organization-domain check are what turn that into an account.

See docs/architecture-v2.md §0.14.
"""

from __future__ import annotations

__all__ = [
    "INSTITUTIONAL",
    "CORPORATE",
    "classify_email",
    "domain_of",
    "is_free_mail",
    "is_institutional",
]


INSTITUTIONAL = "institutional"
CORPORATE = "corporate"


# Matched on domain boundaries, so `kku.edu.tr` matches `edu.tr` while
# `myedu.com` matches nothing. Academic suffixes are country-specific and this
# list is a starting point rather than a standard; extending it is a policy
# decision, not a code change to be made quietly.
INSTITUTIONAL_SUFFIXES = (
    "edu",
    "edu.tr",
    "ac.uk",
    "ac.at",
    "ac.be",
    "ac.il",
    "ac.in",
    "ac.ir",
    "ac.jp",
    "ac.kr",
    "ac.nz",
    "ac.th",
    "ac.za",
    "edu.ar",
    "edu.au",
    "edu.br",
    "edu.cn",
    "edu.hk",
    "edu.mx",
    "edu.pk",
    "edu.sg",
    "edu.tw",
    "edu.ua",
    "edu.vn",
)


# Not exhaustive, and it does not need to be: a domain missing from this list
# still cannot become a corporate account until it is claimed and verified for
# an organization, and that check does not consult this list.
FREE_MAIL_DOMAINS = frozenset(
    {
        "126.com",
        "163.com",
        "aol.com",
        "daum.net",
        "fastmail.com",
        "gmail.com",
        "gmx.com",
        "gmx.de",
        "gmx.net",
        "googlemail.com",
        "hanmail.net",
        "hotmail.com",
        "hotmail.com.tr",
        "icloud.com",
        "inbox.com",
        "live.com",
        "live.com.tr",
        "mail.com",
        "mail.ru",
        "me.com",
        "msn.com",
        "naver.com",
        "outlook.com",
        "outlook.com.tr",
        "proton.me",
        "protonmail.com",
        "qq.com",
        "sina.com",
        "tutanota.com",
        "yandex.com",
        "yandex.ru",
        "yahoo.com",
        "yahoo.com.tr",
        "yandex.com.tr",
        "zoho.com",
    }
)


def domain_of(email: str) -> str | None:
    """The lowercased domain of an address, or None if it is not usable."""

    if not email or "@" not in email:
        return None

    # Whitespace anywhere makes the address unusable, in the local part as much
    # as in the domain: nobody receives mail at "a b@c.com", and accepting it
    # would put an unreachable address behind a verification link.
    if any(character.isspace() for character in email):
        return None

    local, _, domain = email.strip().lower().rpartition("@")

    if not local or not domain or "." not in domain:
        return None

    # A trailing dot is legal in a domain and would otherwise smuggle a
    # different string past the suffix and free-mail comparisons.
    domain = domain.rstrip(".")

    if not domain:
        return None

    return domain


def is_institutional(domain: str) -> bool:
    return any(
        domain == suffix or domain.endswith("." + suffix)
        for suffix in INSTITUTIONAL_SUFFIXES
    )


def is_free_mail(domain: str) -> bool:
    return domain in FREE_MAIL_DOMAINS


def classify_email(email: str) -> tuple[str | None, str]:
    """Return ``(account_kind, reason)``.

    ``account_kind`` is None when the address may not become an account at all,
    and ``reason`` says why -- in a form meant to be shown to the person who
    typed it, because "we refused your address" without a reason is how support
    tickets are born.
    """

    domain = domain_of(email)

    if domain is None:
        return None, "Geçerli bir e-posta adresi girin."

    if is_free_mail(domain):
        return (
            None,
            "Ücretsiz e-posta adresleri kabul edilmiyor. "
            "Lütfen kurumunuzun veya kuruluşunuzun adresini kullanın.",
        )

    if is_institutional(domain):
        return INSTITUTIONAL, ""

    return CORPORATE, ""
