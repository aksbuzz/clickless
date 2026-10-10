"""Outbound requests may only go to public addresses unless an operator explicitly allows more."""
import socket

import pytest

from src.shared.net_guard import OutboundBlocked, check_host, check_url


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("OUTBOUND_ALLOW_HOSTS", raising=False)
    monkeypatch.delenv("OUTBOUND_ALLOW_PRIVATE", raising=False)


NON_PUBLIC = [
    "http://127.0.0.1/",
    "http://localhost:8000/",
    "http://10.0.0.5/",
    "http://192.168.1.10/x",
    "http://172.16.5.4/",
    "http://169.254.169.254/latest/meta-data/",   # cloud metadata service
    "http://[::1]/",
    "http://0.0.0.0/",
    "http://100.64.0.1/",                          # carrier-grade NAT
    "http://[::ffff:127.0.0.1]/",                  # IPv4-mapped loopback
    "http://127.1/",                               # short form of 127.0.0.1
    "http://2130706433/",                          # decimal form of 127.0.0.1
    "http://8.8.8.8@127.0.0.1/",                   # user-info trick
    "http://[fd00::1]/",
    "http://[fe80::1]/",
]


@pytest.mark.parametrize("url", NON_PUBLIC)
def test_non_public_destinations_are_blocked(url):
    with pytest.raises(OutboundBlocked):
        check_url(url)


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://8.8.8.8/", "gopher://8.8.8.8/", "javascript:alert(1)",
    "", "http:///nohost", "//8.8.8.8/x", "8.8.8.8", "http://8.8.8.8:notaport/",
])
def test_only_http_and_https_urls_with_a_host_are_accepted(url):
    with pytest.raises(OutboundBlocked):
        check_url(url)


@pytest.mark.parametrize("url", ["http://8.8.8.8/", "https://1.1.1.1:8443/path?q=1", "https://[2606:4700:4700::1111]/"])
def test_public_addresses_are_allowed(url):
    check_url(url)


def fake_dns(monkeypatch, mapping):
    def getaddrinfo(host, port, *args, **kwargs):
        if host not in mapping:
            raise socket.gaierror("unknown host")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in mapping[host]]
    monkeypatch.setattr("src.shared.net_guard.socket.getaddrinfo", getaddrinfo)


def test_a_hostname_is_judged_by_the_addresses_it_resolves_to(monkeypatch):
    fake_dns(monkeypatch, {"public.example": ["8.8.8.8"], "internal.example": ["10.1.2.3"],
                           "mixed.example": ["8.8.8.8", "10.1.2.3"]})
    check_url("https://public.example/hook")
    with pytest.raises(OutboundBlocked):
        check_url("https://internal.example/hook")
    with pytest.raises(OutboundBlocked):
        check_url("https://mixed.example/hook")          # one private answer is enough to refuse
    with pytest.raises(OutboundBlocked):
        check_url("https://does-not-resolve.example/")   # unresolvable fails closed


def test_operator_can_allow_specific_hosts(monkeypatch):
    fake_dns(monkeypatch, {"db.internal": ["10.9.9.9"], "other.internal": ["10.8.8.8"]})
    monkeypatch.setenv("OUTBOUND_ALLOW_HOSTS", "DB.internal, 127.0.0.1")
    check_url("http://db.internal:5432/")
    check_url("http://127.0.0.1:9000/")
    with pytest.raises(OutboundBlocked):
        check_url("http://other.internal/")


def test_operator_can_allow_all_private_destinations_for_development(monkeypatch):
    monkeypatch.setenv("OUTBOUND_ALLOW_PRIVATE", "true")
    check_url("http://10.0.0.5/")
    check_url("http://169.254.169.254/")


def test_check_host_applies_the_same_rules_for_non_http_clients():
    with pytest.raises(OutboundBlocked):
        check_host("10.0.0.5", 5432)
    with pytest.raises(OutboundBlocked):
        check_host("", 5432)
    check_host("8.8.8.8", 5432)
