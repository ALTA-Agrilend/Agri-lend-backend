# Internal API contract with Amanuel (credit scoring / ML model service)
# Single interaction: POST farmer_id + polygon (GeoJSON object) + crop_type.

from app.core.config import settings
import httpx


class ScoringService:
    def __init__(self):
        self.base_url = settings.amanuel_service_url
        self.client = httpx.AsyncClient(timeout=30)

    @staticmethod
    def normalize_evaluation(payload: dict, fallback_farmer_id: str = "", fallback_crop: str = "") -> dict:
        """Guarantee the canonical evaluation contract regardless of upstream drift:

        {
          "response_id", "farmer_id", "crop_type",
          "credit_evaluation": {"target_crop","final_credit_score","score_range",
                                "raw_geospatial_score_out_of_100",
                                "confidence_rating": {"confidence_percentage","tier"}},
          "categorical_points_breakdown": {...},
          "raw_extracted_sub_scores": {...},
        }
        """
        payload = payload or {}
        ce = payload.get("credit_evaluation") or {}
        conf = ce.get("confidence_rating") or {}

        try:
            final_score = int(ce.get("final_credit_score") or 0)
        except (TypeError, ValueError):
            final_score = 0
        try:
            geo_score = float(ce.get("raw_geospatial_score_out_of_100") or 0)
        except (TypeError, ValueError):
            geo_score = 0.0
        try:
            confidence_pct = float(conf.get("confidence_percentage") or 0)
        except (TypeError, ValueError):
            confidence_pct = 0.0

        return {
            "response_id": payload.get("response_id") or payload.get("evaluation_id") or payload.get("id"),
            "farmer_id": payload.get("farmer_id") or fallback_farmer_id,
            "crop_type": payload.get("crop_type") or fallback_crop,
            "credit_evaluation": {
                "target_crop": ce.get("target_crop") or fallback_crop,
                "final_credit_score": final_score,
                "score_range": ce.get("score_range") or "300-850",
                "raw_geospatial_score_out_of_100": round(geo_score, 2),
                "confidence_rating": {
                    "confidence_percentage": round(confidence_pct, 2),
                    "tier": conf.get("tier") or ("HIGH" if confidence_pct >= 75 else "MEDIUM" if confidence_pct >= 50 else "LOW"),
                },
            },
            "categorical_points_breakdown": payload.get("categorical_points_breakdown") or {},
            "raw_extracted_sub_scores": payload.get("raw_extracted_sub_scores") or {},
        }

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
        return self.normalize_evaluation(response.json(), fallback_farmer_id=farmer_id, fallback_crop=crop_type)

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
