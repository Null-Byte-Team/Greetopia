"""Vision provider boundary. No image inference is enabled in this prototype yet."""
from typing import Protocol, Any

class VisionProvider(Protocol):
    def analyze(self, image_path: str, plant_id: str) -> dict[str, Any]: ...

class NotConfiguredVisionProvider:
    def analyze(self, image_path: str, plant_id: str) -> dict[str, Any]:
        return {
            "configured": False,
            "plant_id": plant_id,
            "wilting": None,
            "discoloration": None,
            "spots_or_pests": None,
            "confidence": None,
            "notes": "Vision inference is not configured; no diagnosis was generated.",
        }
