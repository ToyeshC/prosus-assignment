"""Composition root shared by Streamlit and CLI."""

from pathlib import Path

from .onboarding import DatabaseOnboardingService
from .demo import DemoStateService
from .registry import ConfigStore
from .service import AnalyticsService
from .settings import get_settings


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def config_store(root: Path | None = None) -> ConfigStore:
    root = root or project_root()
    return ConfigStore(root / "config" / "registry.yaml", root / "config" / "acl.yaml")


def analytics_service(root: Path | None = None) -> AnalyticsService:
    root = root or project_root()
    return AnalyticsService(config_store(root), root / "catalogs", get_settings())


def onboarding_service(root: Path | None = None) -> DatabaseOnboardingService:
    root = root or project_root()
    return DatabaseOnboardingService(config_store(root), root / "catalogs")


def demo_state_service(root: Path | None = None) -> DemoStateService:
    root = root or project_root()
    return DemoStateService(config_store(root), root / "catalogs")
