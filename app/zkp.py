
from py_ecc.bn128 import G1, multiply, FQ

def generate_zkp_proof(cert_hash):
    """Generate a simple ZKP proof (commitment) for the certificate hash."""
    try:
        h = int(cert_hash, 16) % FQ.field_modulus
        commitment = multiply(G1, h)
        return str(commitment)
    except Exception as e:
        print(f"Error generating ZKP proof: {e}")
        raise

def verify_zkp_proof(proof, cert_hash):
    """Verify the ZKP proof against the certificate hash."""
    try:
        h = int(cert_hash, 16) % FQ.field_modulus
        recomputed = multiply(G1, h)
        return str(recomputed) == proof
    except Exception as e:
        print(f"Error verifying ZKP proof: {e}")
        raise