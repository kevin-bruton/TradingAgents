"""
SSL/TLS configuration utilities for TradingAgents
"""

import os
import ssl
import certifi
from typing import Dict, Any, Optional


def get_ssl_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create SSL configuration dictionary from the main config.
    
    Args:
        config: Main configuration dictionary
        
    Returns:
        SSL configuration dictionary with cert_bundle, verify, timeout, proxies
    """
    ssl_config = {}
    
    # Certificate bundle configuration - only use if explicitly specified
    cert_bundle = config.get("ssl_cert_bundle")
    if cert_bundle and cert_bundle.strip():
        # Use explicitly specified certificate bundle
        ssl_config["cert_bundle"] = cert_bundle
        ssl_config["verify"] = cert_bundle
    elif not config.get("ssl_verify", True):
        # Only disable SSL verification if explicitly set to false
        ssl_config["verify"] = False
    
    # If no explicit cert bundle and ssl_verify is true (default), 
    # don't set anything - use default behavior
    
    # Timeout configuration
    if config.get("http_timeout"):
        ssl_config["timeout"] = config["http_timeout"]
    
    # Proxy configuration
    proxies = {}
    if config.get("http_proxy"):
        proxies["http"] = config["http_proxy"]
    if config.get("https_proxy"):
        proxies["https"] = config["https_proxy"]
    if proxies:
        ssl_config["proxies"] = proxies
    
    return ssl_config


def setup_global_ssl_config(config: Dict[str, Any]) -> None:
    """
    Set up global SSL configuration for the application.
    This affects all SSL connections made by requests and other libraries.
    Only sets configuration if explicitly specified in environment variables.
    
    Args:
        config: Main configuration dictionary
    """
    # Set environment variables for requests library only if explicitly configured
    cert_bundle = config.get("ssl_cert_bundle")
    if cert_bundle and cert_bundle.strip():
        os.environ["REQUESTS_CA_BUNDLE"] = cert_bundle
        os.environ["CURL_CA_BUNDLE"] = cert_bundle
        print(f"🔒 Using custom SSL certificate bundle: {cert_bundle}")
    
    # Set SSL verification for requests only if explicitly disabled
    if not config.get("ssl_verify", True):
        # Disable SSL warnings when verification is disabled
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        print("⚠️  SSL certificate verification disabled")
    
    # Set proxy environment variables if specified
    if config.get("http_proxy"):
        os.environ["HTTP_PROXY"] = config["http_proxy"]
        print(f"🌐 Using HTTP proxy: {config['http_proxy']}")
    if config.get("https_proxy"):
        os.environ["HTTPS_PROXY"] = config["https_proxy"]
        print(f"🌐 Using HTTPS proxy: {config['https_proxy']}")
    
    # Set timeout if specified
    if config.get("http_timeout"):
        print(f"⏱️  HTTP timeout set to: {config['http_timeout']} seconds")


def create_ssl_context(cert_bundle: Optional[str] = None, verify_ssl: bool = True) -> ssl.SSLContext:
    """
    Create a custom SSL context with specified certificate bundle.
    
    Args:
        cert_bundle: Path to certificate bundle file
        verify_ssl: Whether to verify SSL certificates
        
    Returns:
        Configured SSL context
    """
    if not verify_ssl:
        # Create unverified context (not recommended for production)
        context = ssl._create_unverified_context()
    else:
        # Create default context
        context = ssl.create_default_context()
        
        if cert_bundle:
            # Load custom certificate bundle
            context.load_verify_locations(cafile=cert_bundle)
    
    return context


def get_certificate_info() -> Dict[str, str]:
    """
    Get information about available certificate bundles.
    
    Returns:
        Dictionary with certificate bundle information
    """
    info = {}
    
    # Check certifi bundle
    try:
        import certifi
        info["certifi_bundle"] = certifi.where()
    except ImportError:
        info["certifi_bundle"] = "Not available (certifi not installed)"
    
    # Check environment variables
    info["env_ca_bundle"] = os.getenv("REQUESTS_CA_BUNDLE", "Not set")
    info["env_curl_bundle"] = os.getenv("CURL_CA_BUNDLE", "Not set")
    
    # Check system certificate stores
    common_cert_paths = [
        "/etc/ssl/certs/ca-certificates.crt",  # Debian/Ubuntu
        "/etc/pki/tls/certs/ca-bundle.crt",    # RedHat/CentOS
        "/usr/local/share/certs/ca-root-nss.crt",  # FreeBSD
        "/etc/ssl/cert.pem",                   # OpenBSD
        "/System/Library/OpenSSL/certs/cert.pem",  # macOS
    ]
    
    available_system_certs = []
    for path in common_cert_paths:
        if os.path.exists(path):
            available_system_certs.append(path)
    
    info["system_cert_bundles"] = available_system_certs
    
    return info