from typing import Any

import httpx
from loguru import logger
from pydantic import Field
from pydantic import SecretStr

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.mngr.errors import ProviderError


class MngrRemoteClient(FrozenModel):
    """HTTP client for communicating with a remote mngr API server."""

    base_url: str = Field(description="Base URL of the remote mngr API server")
    token: SecretStr = Field(description="Bearer token for authenticating")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token.get_secret_value()}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}{path}"

    def list_agents(self) -> list[dict[str, Any]]:
        """Fetch the agent list from the remote API server."""
        try:
            response = httpx.get(self._url("/api/agents"), headers=self._headers(), timeout=30.0)
            response.raise_for_status()
            data = response.json()
            for error in data.get("errors", []):
                logger.warning(
                    "Remote mngr at {} reported error: {} - {}",
                    self.base_url,
                    error.get("error_type", "unknown"),
                    error.get("message", "unknown"),
                )
            return data.get("agents", [])
        except httpx.HTTPError as e:
            logger.warning("Failed to fetch agents from remote mngr at {}: {}", self.base_url, e)
            raise ProviderError(f"Failed to connect to remote mngr API at {self.base_url}: {e}") from e

    def send_message(self, agent_id: str, message: str) -> None:
        """Send a message to an agent on the remote server."""
        try:
            response = httpx.post(
                self._url(f"/api/agents/{agent_id}/message"),
                headers=self._headers(),
                json={"message": message},
                timeout=30.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise ProviderError(f"Failed to send message to agent {agent_id}: {e}") from e

    def stop_agent(self, agent_id: str) -> None:
        """Stop an agent on the remote server."""
        try:
            response = httpx.post(
                self._url(f"/api/agents/{agent_id}/stop"),
                headers=self._headers(),
                timeout=30.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise ProviderError(f"Failed to stop agent {agent_id}: {e}") from e

    def record_activity(self, agent_id: str) -> None:
        """Record activity for an agent on the remote server."""
        try:
            response = httpx.post(
                self._url(f"/api/agents/{agent_id}/activity"),
                headers=self._headers(),
                json={},
                timeout=10.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            logger.debug("Failed to record activity for agent {}: {}", agent_id, e)
