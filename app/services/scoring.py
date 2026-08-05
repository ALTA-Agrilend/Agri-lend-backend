# Internal API contract with Amanuel (credit scoring / ML model service)
# Single interaction: POST farmer_id + polygon (GeoJSON object) + crop_type.

from app.core.config import settings
import httpx


class ScoringService:
    def __init__(self):
        self.base_url = settings.amanuel_service_url
        self.client = httpx.AsyncClient(timeout=30)

    async def get_credit_score(self, farmer_id: str, polygon: dict | None, crop_type: str) -> dict:
        response = await self.client.post(
            f"{self.base_url}/evaluate-credit",
            json={
                "farmer_id": farmer_id,
                "polygon": polygon,
                "crop_type": crop_type,
            },
        )
        response.raise_for_status()
        return response.json()

    async def get_heatmap_data(self, params: dict) -> dict:
        response = await self.client.get(
            f"{self.base_url}/api/v1/heatmap",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    async def get_model_metrics(self) -> dict:
        response = await self.client.get(f"{self.base_url}/api/v1/metrics")
        response.raise_for_status()
        return response.json()

    async def close(self):
        await self.client.aclose()
