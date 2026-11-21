"""Use the target desktop's trusted certificates for GitHub HTTPS requests."""

import os
from pathlib import Path
import ssl
import sys


def tls_context() -> ssl.SSLContext:
    # Relocatable Python builds can retain the build machine's OpenSSL paths.
    # Preserve explicit trust-store settings and Windows' native store loading.
    if not (os.environ.get("SSL_CERT_FILE") or os.environ.get("SSL_CERT_DIR")):
        if sys.platform == "darwin":
            candidates = ("/etc/ssl/cert.pem",)
        elif sys.platform.startswith("linux"):
            candidates = ("/etc/ssl/certs/ca-certificates.crt",
                          "/etc/pki/tls/certs/ca-bundle.crt",
                          "/etc/ssl/ca-bundle.pem", "/etc/ssl/cert.pem")
        else:
            candidates = ()
        for bundle in candidates:
            if Path(bundle).is_file():
                return ssl.create_default_context(cafile=bundle)
    return ssl.create_default_context()
