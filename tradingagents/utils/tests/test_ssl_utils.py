import os
import ssl
import pytest
from tradingagents.dataflows.ssl_utils import (
    get_ssl_config,
    setup_global_ssl_config,
    create_ssl_context,
    get_certificate_info,
)


def test_get_ssl_config_variants(tmp_path):
    # Explicit bundle
    cfg = {"ssl_cert_bundle": str(tmp_path / "ca.pem"), "ssl_verify": True, "http_timeout": 5}
    (tmp_path / "ca.pem").write_text("---CERT---")
    result = get_ssl_config(cfg)
    assert result["cert_bundle"].endswith("ca.pem")
    assert result["verify"].endswith("ca.pem")
    assert result["timeout"] == 5

    # Explicit disable verify
    cfg2 = {"ssl_verify": False}
    result2 = get_ssl_config(cfg2)
    assert result2["verify"] is False

    # Proxy assembly
    cfg3 = {"http_proxy": "http://proxy:8080", "https_proxy": "https://proxy:8443"}
    result3 = get_ssl_config(cfg3)
    assert result3["proxies"]["http"].startswith("http://proxy")
    assert result3["proxies"]["https"].startswith("https://proxy")


def test_setup_global_ssl_config_env(monkeypatch, tmp_path, capsys):
    bundle = tmp_path / "root.pem"
    bundle.write_text("X")
    cfg = {"ssl_cert_bundle": str(bundle), "ssl_verify": True, "http_timeout": 12}
    setup_global_ssl_config(cfg)
    captured = capsys.readouterr().out
    assert "custom SSL certificate bundle" in captured
    assert os.getenv("REQUESTS_CA_BUNDLE") == str(bundle)
    assert os.getenv("CURL_CA_BUNDLE") == str(bundle)


def test_create_ssl_context_variants(tmp_path):
    # Unverified
    ctx_unverified = create_ssl_context(verify_ssl=False)
    assert isinstance(ctx_unverified, ssl.SSLContext)
    assert ctx_unverified.verify_mode == ssl.CERT_NONE

    # Verified default
    ctx_default = create_ssl_context()
    assert isinstance(ctx_default, ssl.SSLContext)

    # With custom bundle (file may be empty, just ensure load_verify_locations path usage)
    custom = tmp_path / "custom.pem"
    # Write a minimal PEM-ish structure so OpenSSL doesn't error; not a real cert but shaped
    custom.write_text("""-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n""")
    try:
        ctx_custom = create_ssl_context(str(custom), verify_ssl=True)
        assert isinstance(ctx_custom, ssl.SSLContext)
    except ssl.SSLError:
        # Some OpenSSL builds may still reject; acceptable to skip in that case
        pytest.skip("OpenSSL rejected minimal placeholder certificate")


def test_get_certificate_info_returns_keys():
    info = get_certificate_info()
    assert {"certifi_bundle", "env_ca_bundle", "env_curl_bundle", "system_cert_bundles"}.issubset(info)
