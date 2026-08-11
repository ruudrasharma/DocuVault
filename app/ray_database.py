
import ray
from ray import serve
from app.database_models import CertificateRecord
from app import db

ray.init(ignore_reinit_error=True)

@serve.deployment
class RayDatabase:
    def __init__(self):
        self.session = db.session

    def add_record(self, hash_value, institution, encrypted_metadata):
        try:
            record = CertificateRecord(
                hash_value=hash_value,
                institution=institution,
                is_valid=True,
                encrypted_metadata=encrypted_metadata
            )
            self.session.add(record)
            self.session.commit()
            return True
        except Exception as e:
            print(f"Ray DB add error: {e}")
            return False

    def check_hash(self, hash_value):
        try:
            return self.session.query(CertificateRecord).filter_by(hash_value=hash_value).first() is not None
        except Exception as e:
            print(f"Ray DB check error: {e}")
            return False

# Deploy Ray database service
ray_database = RayDatabase.bind()
