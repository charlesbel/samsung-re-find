import base64
import hashlib

from samsung_find.crypto import code_challenge


def test_rfc7636_code_challenge():
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"  # pragma: allowlist secret
    expected = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"  # pragma: allowlist secret
    assert code_challenge(verifier) == expected


def test_challenge_is_unpadded_urlsafe_sha256():
    verifier = "a" * 43
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert code_challenge(verifier) == expected
