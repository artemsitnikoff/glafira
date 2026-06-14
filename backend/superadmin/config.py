import os
from typing import Optional


class SuperAdminConfig:
    """Configuration for superadmin service.

    All secrets are required, no defaults to ensure fail-closed security.
    """

    def __init__(self):
        # Required credentials - fail-closed if not set
        self.SUPERADMIN_USER: Optional[str] = os.getenv("SUPERADMIN_USER")
        self.SUPERADMIN_PASSWORD_HASH: Optional[str] = os.getenv("SUPERADMIN_PASSWORD_HASH")
        self.SUPERADMIN_JWT_SECRET: Optional[str] = os.getenv("SUPERADMIN_JWT_SECRET")

        # Optional test results path
        self.TEST_RESULTS_PATH: str = os.getenv(
            "SUPERADMIN_TEST_RESULTS_PATH",
            "/app/storage/test-results.xml"
        )

    @property
    def is_configured(self) -> bool:
        """Check if superadmin is properly configured for login"""
        return bool(
            self.SUPERADMIN_USER and
            self.SUPERADMIN_PASSWORD_HASH and
            self.SUPERADMIN_JWT_SECRET
        )


config = SuperAdminConfig()