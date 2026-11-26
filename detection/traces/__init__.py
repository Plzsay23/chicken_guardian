"""Small rodent-trace detection (droppings, feed pellets) for the poultry-house patrol robot."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CFG = ROOT / "configs" / "traces.yaml"


def load_cfg(path=None):
    import yaml

    with open(path or DEFAULT_CFG, encoding="utf-8") as f:
        return yaml.safe_load(f)
